"use client";

import { useMemo, useRef, useState } from "react";
import { RunDetail } from "@/lib/api";
import { lineChanges, unifiedDiff } from "@/lib/diff";
import { cx, fmtMs, fmtSpeedup, STOP_LABEL } from "@/lib/format";
import { Outcome } from "@/lib/workspace";
import { DiffView } from "@/components/DiffView";
import { TraceTimeline } from "@/components/TraceTimeline";
import { Segmented } from "@/components/ui";
import { CodePane } from "@/components/workspace/CodeEditor";
import { Accordion, BigButton, Notice } from "@/components/workspace/parts";

function download(content: string, filename: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function Metric({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-[12px] border border-rule bg-surface p-4">
      <div className="text-[12.5px] font-medium text-muted">{label}</div>
      <div className={cx("mt-1 text-[26px] font-semibold tracking-tight", tone === "good" && "text-accent", tone === "bad" && "text-bad")}>{value}</div>
      {sub && <div className="mt-0.5 text-[12.5px] text-muted">{sub}</div>}
    </div>
  );
}

export function ResultsView({
  run, outcome, fileName, language, onAnother, onBack,
}: {
  run: RunDetail; outcome: Outcome; fileName: string; language: "c" | "cpp"; onAnother: () => void; onBack: () => void;
}) {
  const [view, setView] = useState<"side" | "diff">("side");
  const [copied, setCopied] = useState<"" | "code" | "cmd">("");
  const left = useRef<HTMLDivElement>(null);
  const right = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);

  const { original, optimized } = { original: outcome.originalSource, optimized: outcome.optimizedSource };
  const changes = useMemo(() => lineChanges(original, optimized), [original, optimized]);
  const diff = useMemo(() => unifiedDiff(original, optimized, 3, fileName), [original, optimized, fileName]);

  const buildCmd = `${language === "c" ? "gcc" : "g++"} ${outcome.flags.join(" ")} ${fileName} -o program -lm`.replace(/\s+/g, " ");

  function copy(text: string, what: "code" | "cmd") {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(what);
      setTimeout(() => setCopied(""), 2000);
    });
  }

  function mirror(from: HTMLDivElement, to: HTMLDivElement | null) {
    if (!to || syncing.current) return;
    syncing.current = true;
    to.scrollTop = from.scrollTop;
    to.scrollLeft = from.scrollLeft;
    requestAnimationFrame(() => { syncing.current = false; });
  }

  const improved = outcome.kind === "improved";
  const technical = (
    <Accordion title="Technical details" hint="Agent steps, configuration and statistics">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] sm:grid-cols-4">
        {[
          ["Run ID", run.run_id.slice(0, 12)],
          ["Program", run.program_id],
          ["Attempts", String(outcome.attempts)],
          ["Stopped because", STOP_LABEL[run.state?.stop_reason ?? ""] ?? (run.state?.stop_reason || "—")],
          ["Method", String(run.config?.variant ?? "—")],
          ["Compiler settings", outcome.flags.join(" ") || "—"],
          ["Significance (p)", outcome.pValue == null ? "—" : outcome.pValue.toFixed(4)],
          ["AI tokens used", run.state ? String(run.state.usage.prompt_tokens + run.state.usage.completion_tokens) : "—"],
        ].map(([k, v]) => (
          <div key={k}>
            <dt className="text-muted">{k}</dt>
            <dd className="break-words font-mono text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {(run.events?.length ?? 0) > 0 && <TraceTimeline events={run.events} endTime={run.state?.finished_at} />}
      <a className="inline-block text-[13px] font-medium text-info underline underline-offset-2" href={`/run/?id=${run.run_id}`}>Open in the full run inspector →</a>
    </Accordion>
  );

  const actions = (
    <div className="flex flex-wrap gap-3">
      <BigButton onClick={onAnother}>Optimize another program</BigButton>
      <BigButton variant="ghost" onClick={onBack}>← Back to editor</BigButton>
    </div>
  );

  if (!improved) {
    const title = outcome.kind === "no_gain" ? "No faster version found" : outcome.kind === "cancelled" ? "Stopped" : outcome.kind === "failed" ? "The optimization didn't finish" : "No result yet";
    return (
      <div className="mx-auto max-w-[760px] space-y-6">
        <Notice tone={outcome.kind === "no_gain" ? "info" : outcome.kind === "cancelled" ? "warn" : "bad"} title={title}>{outcome.message}</Notice>
        {outcome.kind === "no_gain" && (
          <p className="text-[14px] text-muted">
            This isn&apos;t an error. Changes are only kept when they&apos;re faster by a meaningful margin <em>and</em> give identical output. Try the &ldquo;Smart rewrite&rdquo; method, more attempts, or a bigger example input so there&apos;s enough running time to measure.
          </p>
        )}
        {outcome.kind === "failed" && /original code/i.test(outcome.message) && (
          <p className="text-[14px] text-muted">We run your original code first to learn what correct output looks like. Fix the problem above in the editor and try again.</p>
        )}
        {actions}
        {technical}
      </div>
    );
  }

  const v = outcome.validation;
  const validationTitle = v === "verified" ? "Verified: same output, no memory problems" : v === "output_only" ? "Same output on all test inputs" : "Not verified";

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <h2 className="text-[24px] font-semibold tracking-tight text-ink">
          {outcome.speedup ? <>Your code runs <span className="text-accent">{fmtSpeedup(outcome.speedup)}</span> faster</> : "A faster version was found"}
        </h2>
        <Notice tone={v === "verified" ? "good" : v === "output_only" ? "info" : "bad"} title={validationTitle}>
          {outcome.validationNote} It was only checked on the example inputs used for this run, so test it on your own data before relying on it.
        </Notice>
        {outcome.lowPrecision && (
          <Notice tone="warn" title="Short running time">
            The program ran for only a few milliseconds, so this speed-up is a rough estimate. A larger example input gives a more reliable number.
          </Notice>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Original runtime" value={outcome.originalMs == null ? "—" : fmtMs(outcome.originalMs)} />
        <Metric label="Optimized runtime" value={outcome.optimizedMs == null ? "—" : fmtMs(outcome.optimizedMs)} tone="good" />
        <Metric label="Speed-up" value={outcome.speedup == null ? "—" : fmtSpeedup(outcome.speedup)} tone="good" sub="median, timed side by side" />
        <Metric label="Correctness" value={v === "verified" ? "Verified" : v === "output_only" ? "Output matches" : "Not verified"} tone={v === "verified" ? "good" : v === "unverified" ? "bad" : undefined} sub={v === "verified" ? "output + memory safety" : v === "output_only" ? "memory check unavailable" : undefined} />
      </div>

      {!outcome.sourceChanged && (
        <Notice tone="info" title="The speed-up comes from compiler settings, not from changes to your code">
          {"Your source is unchanged. Compile it like this to get the faster build:\n"}
          <code className="mt-2 block break-all rounded-[6px] bg-sunken px-3 py-2 font-mono text-[12.5px]">{buildCmd}</code>
          <button type="button" onClick={() => copy(buildCmd, "cmd")} className="mt-2 text-[13px] font-medium text-info underline underline-offset-2">
            {copied === "cmd" ? "Copied" : "Copy build command"}
          </button>
        </Notice>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          value={view}
          onChange={setView}
          options={[{ value: "side", label: "Side by side" }, { value: "diff", label: "Changes only" }]}
        />
        <div className="flex flex-wrap gap-2">
          <BigButton variant="ghost" onClick={() => copy(optimized, "code")}>{copied === "code" ? "✓ Copied" : "Copy optimized code"}</BigButton>
          <BigButton variant="ghost" onClick={() => download(optimized, `optimized_${fileName}`)}>Download optimized code</BigButton>
          {outcome.sourceChanged && <BigButton variant="ghost" onClick={() => download(diff, "optimization.patch")}>Download patch</BigButton>}
        </div>
      </div>

      {view === "side" ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CodePane title="Original code" code={original} tint={changes.removed} tone="del" scrollRef={left} onScroll={(el) => mirror(el, right.current)} />
          <CodePane title="Optimized code" code={optimized} tint={changes.added} tone="add" scrollRef={right} onScroll={(el) => mirror(el, left.current)} />
        </div>
      ) : (
        <DiffView diff={diff} maxHeight={520} />
      )}

      {actions}
      {technical}
    </div>
  );
}
