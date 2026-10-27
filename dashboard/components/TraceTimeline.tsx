"use client";

import { useEffect, useMemo, useState } from "react";
import { RunEvent } from "@/lib/api";
import { AGENTS, AGENT_LABEL, cx, fmtMs, fmtTokens, fmtUsd, laneColor } from "@/lib/format";

type Span = { agent: string; attempt: number | null; start: number; end: number; open: boolean; ev?: RunEvent };

function buildSpans(events: RunEvent[], now: number, endTime?: number) {
  const runStart = events.find((e) => e.type === "run_start")?.t ?? events[0]?.t ?? now;
  const runEnd = events.find((e) => e.type === "run_end")?.t ?? endTime;
  const spans: Span[] = [];
  const open = new Map<string, RunEvent>();
  for (const e of events) {
    const key = `${e.agent}:${e.attempt ?? "-"}`;
    if (e.type === "step_start") open.set(key, e);
    if (e.type === "step_end" && e.agent) {
      const start = open.get(key)?.t ?? e.t - (e.dur_ms ?? 0) / 1000;
      open.delete(key);
      spans.push({ agent: e.agent, attempt: e.attempt ?? null, start, end: e.t, open: false, ev: e });
    }
  }
  for (const [, e] of open) {
    if (e.agent) spans.push({ agent: e.agent, attempt: e.attempt ?? null, start: e.t, end: runEnd ?? now, open: !runEnd });
  }
  const attempts = events.filter((e) => e.type === "attempt_end");
  const end = runEnd ?? Math.max(now, ...spans.map((s) => s.end));
  return { runStart, end, spans, attempts, live: !runEnd };
}

export function TraceTimeline({ events, endTime }: { events: RunEvent[]; endTime?: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [hover, setHover] = useState<Span | null>(null);
  const live = !endTime && !events.some((e) => e.type === "run_end");
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 400);
    return () => clearInterval(id);
  }, [live]);

  const { runStart, end, spans, attempts } = useMemo(() => buildSpans(events, now, endTime), [events, now, endTime]);
  const total = Math.max(end - runStart, 1);
  const lanes = AGENTS.filter((a) => spans.some((s) => s.agent === a));
  const x = (t: number) => `${((t - runStart) / total) * 100}%`;
  const ticks = niceTicks(total);

  if (!events.length) return <div className="py-8 text-center text-[13px] text-muted">Waiting for the first step…</div>;

  return (
    <div>
      <div className="relative">
        {/* time axis */}
        <div className="relative ml-[118px] h-5 border-b border-rule">
          {ticks.map((t) => (
            <div key={t} className="absolute top-0 -translate-x-1/2 font-mono text-[10px] text-faint" style={{ left: `${(t / total) * 100}%` }}>
              {t >= 60 ? `${(t / 60).toFixed(t % 60 ? 1 : 0)}m` : `${t}s`}
            </div>
          ))}
        </div>
        <div className="relative">
          {/* attempt boundaries */}
          <div className="pointer-events-none absolute inset-y-0 left-[118px] right-0">
            {ticks.map((t) => (
              <div key={t} className="absolute inset-y-0 border-l border-rule/60" style={{ left: `${(t / total) * 100}%` }} />
            ))}
            {attempts.map((a, i) => (
              <div key={`${a.attempt}`} className="absolute inset-y-0 border-l border-dashed" style={{ left: x(a.t), borderColor: a.verdict?.accepted ? "rgb(var(--accent))" : "rgb(var(--faint))" }}>
                <span style={{ top: i % 2 ? 15 : -1, ...((a.t - runStart) / total > 0.85 ? { right: 4 } : { left: 4 }) }} className={cx("absolute whitespace-nowrap rounded-[3px] px-1 font-mono text-[9.5px]", a.verdict?.accepted ? "bg-accent text-paper" : "bg-sunken text-muted")}>
                  A{a.attempt} {a.verdict?.accepted ? `${a.verdict.speedup.toFixed(2)}×` : "✕"}
                </span>
              </div>
            ))}
          </div>
          {lanes.map((agent) => (
            <div key={agent} className="flex h-[30px] items-center border-b border-rule/70 last:border-b-0">
              <div className="flex w-[118px] shrink-0 items-center gap-2 pr-3 text-[12px]">
                <span className="inline-block h-[8px] w-[8px] rounded-[2px]" style={{ background: laneColor(agent) }} />
                <span className="truncate text-muted">{AGENT_LABEL[agent] ?? agent}</span>
              </div>
              <div className="relative h-full flex-1">
                {spans.filter((s) => s.agent === agent).map((s, i) => (
                  <button
                    key={i}
                    onMouseEnter={() => setHover(s)}
                    onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(s)}
                    className={cx("absolute top-[7px] h-[16px] min-w-[3px] rounded-[3px] outline-none ring-ink/40 focus-visible:ring-2", s.open && "live-dot", s.ev?.status === "error" && "ring-1 ring-bad")}
                    style={{ left: x(s.start), width: `${((s.end - s.start) / total) * 100}%`, background: laneColor(agent, s.open ? 0.55 : 0.9) }}
                    aria-label={`${agent} ${s.ev?.summary ?? ""}`}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 min-h-[44px] rounded-[6px] border border-rule bg-sunken px-3 py-2 text-[12px]">
        {hover ? (
          <div className="flex flex-col gap-0.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
              <span className="font-medium">{AGENT_LABEL[hover.agent]}</span>
              {hover.attempt != null && <span className="font-mono text-muted">attempt {hover.attempt}</span>}
              <span className="num">{fmtMs((hover.end - hover.start) * 1000)}</span>
              {hover.ev && (hover.ev.tokens_in || hover.ev.tokens_out) ? (
                <span className="num text-muted">
                  {fmtTokens(hover.ev.tokens_in)} in / {fmtTokens(hover.ev.tokens_out)} out · {fmtUsd(hover.ev.cost_usd)}
                </span>
              ) : null}
              {hover.ev?.model && hover.ev.model !== "none" && <span className="font-mono text-faint">{hover.ev.model}</span>}
            </div>
            <div className="truncate text-muted">{hover.open ? "running…" : hover.ev?.summary}</div>
          </div>
        ) : (
          <span className="text-faint">Hover a span for timing, tokens and what the agent did.</span>
        )}
      </div>
    </div>
  );
}

function niceTicks(totalS: number): number[] {
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200];
  const step = steps.find((s) => totalS / s <= 8) ?? 1800;
  const out = [];
  for (let t = 0; t <= totalS; t += step) out.push(t);
  return out;
}
