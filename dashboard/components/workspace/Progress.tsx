"use client";

import { useEffect, useState } from "react";
import { RunEvent } from "@/lib/api";
import { cx } from "@/lib/format";
import { latestStatus, stagesFrom } from "@/lib/workspace";
import { BigButton, Notice } from "@/components/workspace/parts";

export function ProgressView({
  status, events, maxAttempts, startedAt, queuePosition, onCancel, cancelling,
}: {
  status: string; events: RunEvent[]; maxAttempts: number; startedAt: number; queuePosition: number; onCancel: () => void; cancelling: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const elapsed = Math.max(0, Math.round((now - startedAt) / 1000));
  const attemptsDone = events.filter((e) => e.type === "attempt_end").length;
  const started = events.some((e) => e.type === "run_start");
  const stages = stagesFrom(events);
  const line = latestStatus(events);

  const headline = status === "queued"
    ? queuePosition > 1 ? `Waiting for your turn (${queuePosition - 1} ahead of you)…` : "Getting ready…"
    : !started ? "Checking that your original code runs…" : "Working on your code…";

  return (
    <div className="mx-auto max-w-[720px] space-y-6">
      <div className="rounded-[14px] border border-rule bg-surface p-6 sm:p-8">
        <div className="flex items-start gap-4">
          <span className="mt-1 inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-[3px] border-rule border-t-accent" aria-hidden />
          <div className="min-w-0">
            <h2 className="text-[20px] font-semibold tracking-tight text-ink" aria-live="polite">{headline}</h2>
            <p className="mt-1 text-[14px] text-muted">
              {elapsed}s elapsed
              {started && <> · {attemptsDone === 0 ? "first attempt in progress" : `${attemptsDone} of up to ${maxAttempts} attempts finished`}</>}
            </p>
          </div>
        </div>

        {line && <p className="mt-5 rounded-[8px] bg-sunken px-3.5 py-2.5 text-[13.5px] text-ink" aria-live="polite">{line}</p>}

        <ul className="mt-6 space-y-2.5" aria-label="Steps">
          {stages.map((s) => (
            <li key={s.label} className={cx("flex items-center gap-3 text-[14.5px]", s.state === "waiting" ? "text-faint" : "text-ink")}>
              <span
                aria-hidden
                className={cx(
                  "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold",
                  s.state === "done" && "bg-accent text-paper",
                  s.state === "active" && "border-2 border-accent",
                  s.state === "waiting" && "border-2 border-rule",
                )}
              >
                {s.state === "done" ? "✓" : s.state === "active" ? <span className="h-2 w-2 animate-pulse rounded-full bg-accent" /> : ""}
              </span>
              <span className={s.state === "active" ? "font-medium" : undefined}>{s.label}</span>
              <span className="sr-only">{s.state}</span>
            </li>
          ))}
        </ul>

        <p className="mt-6 text-[13px] text-muted">
          Every candidate is compiled, checked against your original&apos;s output and timed on this machine, so this can take a few minutes. You&apos;ll be taken to the results automatically.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <BigButton variant="ghost" onClick={onCancel} disabled={cancelling}>{cancelling ? "Stopping…" : "Stop"}</BigButton>
      </div>
      {cancelling && <Notice tone="info">Stopping. The step that is running right now may take a moment to wind down.</Notice>}
    </div>
  );
}
