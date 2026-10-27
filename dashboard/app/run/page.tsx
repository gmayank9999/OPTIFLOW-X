"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api, Attempt, RunDetail, RunEvent, streamUrl, useApi } from "@/lib/api";
import { unifiedDiff } from "@/lib/diff";
import { AGENT_LABEL, cx, fmtMs, fmtPct, fmtSpeedup, fmtTokens, fmtUsd, laneColor, REASON_LABEL, STOP_LABEL } from "@/lib/format";
import { DiffView } from "@/components/DiffView";
import { StripPlot } from "@/components/StripPlot";
import { TraceTimeline } from "@/components/TraceTimeline";
import { Button, Empty, ErrorNote, KV, PageHeader, Panel, Pill, Skeleton, Stat, StatRow, StatusPill, TableWrap, Td, Th, VerdictPill } from "@/components/ui";

export default function RunPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40" />}>
      <RunView />
    </Suspense>
  );
}

function RunView() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const { data, error, reload } = useApi<RunDetail>(id ? `/runs/${id}` : null);
  const [live, setLive] = useState<RunEvent[] | null>(null);

  // Live stream: the server replays the backlog first, then pushes new
  // events until run_end. Then we refetch the saved report.
  useEffect(() => {
    if (!id || !data || data.state) return;
    const ws = new WebSocket(streamUrl(id));
    const buf: RunEvent[] = [];
    ws.onmessage = (m) => {
      const ev = JSON.parse(m.data) as RunEvent;
      buf.push(ev);
      setLive([...buf]);
      if (ev.type === "run_end") setTimeout(reload, 600);
    };
    return () => ws.close();
  }, [id, data?.state ? "saved" : "live"]); // eslint-disable-line react-hooks/exhaustive-deps

  const events = data?.state ? data.events : live ?? data?.events ?? [];
  const attempts = useMemo<Attempt[]>(() => (data?.state ? data.state.history : attemptsFromEvents(events)), [data, events]);

  if (!id) return <Empty title="No run selected" />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-64" /></div>;

  const status = data.state ? (data.state.error ? "failed" : "done") : events.some((e) => e.type === "run_end") ? "done" : data.status;
  const cfg = data.config ?? {};
  const runEnd = events.find((e) => e.type === "run_end");
  const best = data.state?.best ?? null;
  const bestSpeedup = best?.speedup ?? runEnd?.best_speedup ?? Math.max(1, ...attempts.filter((a) => a.verdict?.accepted).map((a) => a.verdict.speedup));
  const accepted = attempts.filter((a) => a.verdict?.accepted);
  const usage = data.state?.usage ?? runEnd?.usage ?? sumUsage(events);
  const wall = data.state ? data.state.finished_at - data.state.started_at : events.length ? (events[events.length - 1].t - events[0].t) : 0;
  const bestAttempt = attempts.find((a) => a.attempt === best?.attempt) ?? accepted[accepted.length - 1];
  const profile = data.state?.profile ?? events.find((e) => e.type === "step_end" && e.agent === "profiler")?.data;

  async function again() {
    const res = await api<{ run_id: string }>("/runs", {
      method: "POST",
      body: JSON.stringify({
        program_id: data!.program_id, architecture: cfg.architecture, messaging: cfg.messaging,
        prompt_style: cfg.prompt_style, variant: cfg.variant, max_attempts: cfg.max_attempts,
      }),
    });
    router.push(`/run/?id=${res.run_id}`);
  }

  return (
    <>
      <PageHeader
        eyebrow={`Run · ${id.slice(0, 8)}`}
        title={<span className="font-mono text-[24px] md:text-[28px]">{data.program_id}</span>}
        actions={<><Button variant="ghost" href={`/program/?id=${data.program_id}`}>Program</Button><Button variant="ghost" onClick={again}>Run again</Button></>}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusPill status={status} />
          {["flags_only", "rule_only"].includes(cfg.variant) ? (
            <Pill tone="outline">{String(cfg.variant).replace("_", " ")} baseline · no LLM</Pill>
          ) : (
            <>
              <Pill tone="outline">{cfg.architecture}</Pill>
              <Pill tone="outline">{cfg.messaging}</Pill>
              <Pill tone="outline">{cfg.prompt_style}</Pill>
              <Pill tone="outline">{cfg.model_assignment}</Pill>
              {cfg.persona && cfg.persona !== "default" && <Pill tone="outline">persona: {cfg.persona}</Pill>}
              {cfg.critic_backend === "adk_a2a" && <Pill tone="info" title="Rejection feedback came from a Google ADK agent over the A2A protocol">critic: ADK via A2A</Pill>}
              {cfg.variant !== "full" && <Pill tone="warn">{cfg.variant}</Pill>}
            </>
          )}
          {data.state?.stop_reason && <span className="ml-1 text-[12px] text-muted">stopped: {STOP_LABEL[data.state.stop_reason] ?? data.state.stop_reason}</span>}
        </div>
      </PageHeader>

      {(data.state?.error || data.error) && (
        <div className="mb-6 rounded-[7px] border border-bad/30 bg-bad-soft px-4 py-3 font-mono text-[12px] text-bad">
          {(data.state?.error || data.error || "").split("\n")[0]}
        </div>
      )}

      <StatRow>
        <Stat label="Best speedup" value={fmtSpeedup(bestSpeedup)} tone={bestSpeedup >= 1.05 ? "accent" : undefined} sub={best?.strategies?.length ? best.strategies.join(" + ") : accepted.length ? "" : "no accepted candidate"} />
        <Stat label="Attempts" value={`${accepted.length}/${attempts.length}`} sub="accepted / judged" />
        <Stat label="Tokens" value={fmtTokens(usage.prompt_tokens + usage.completion_tokens)} sub={`${fmtTokens(usage.prompt_tokens)} in · ${fmtTokens(usage.completion_tokens)} out`} />
        <Stat label="LLM cost" value={fmtUsd(usage.cost_usd)} sub={`${usage.calls ?? 0} calls`} />
        <Stat label="Wall time" value={wall ? fmtMs(wall * 1000) : "—"} sub={status === "running" ? "still running" : undefined} />
      </StatRow>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px] xl:items-start">
        <Panel eyebrow="Trace" title="Agent timeline" right={status === "running" ? <StatusPill status="running" /> : undefined}>
          <TraceTimeline events={events} endTime={data.state?.finished_at} />
        </Panel>
        <div className="flex flex-col gap-6">
          <Panel eyebrow="Receipts" title="Why the best candidate was accepted">
            {bestAttempt?.compare ? <Checklist a={bestAttempt} /> : <p className="text-[13px] text-muted">{status === "running" ? "No accepted candidate yet." : "Nothing was accepted in this run; the original program stands."}</p>}
          </Panel>
          {profile && (
            <Panel eyebrow="Profile" title="Baseline at -O2 (stability table)">
              <KV k="Median runtime" v={fmtMs(profile.baseline_runtime_ms ?? profile.baseline_ms)} />
              <KV k="IPC" v={profile.ipc?.toFixed(2) ?? "—"} />
              <KV k="L1 miss rate" v={fmtPct(profile.l1_miss_rate)} />
              <KV k="LLC miss rate" v={fmtPct(profile.llc_miss_rate)} />
              {profile.hotspots?.[0] && <KV k="Hottest loop" v={`L${profile.hotspots[0].start_line}–${profile.hotspots[0].end_line} · ${profile.hotspots[0].time_pct.toFixed(0)}%`} />}
            </Panel>
          )}
        </div>
      </div>

      <div className="mt-8">
        <div className="eyebrow mb-3">Attempts</div>
        {attempts.length === 0 ? (
          <Empty title={status === "running" ? "Analyzing and profiling…" : "No attempts were made"} />
        ) : (
          <div className="flex flex-col gap-4">
            {attempts.map((a) => <AttemptCard key={a.attempt} a={a} isBest={a.attempt === best?.attempt} />)}
          </div>
        )}
      </div>

      {best && data.original_source && best.candidate.source && best.attempt > 0 && (
        <Panel className="mt-8" eyebrow="Result" title={`Original → best (attempt ${best.attempt}, ${best.candidate.flags.join(" ")})`}>
          <DiffView diff={unifiedDiff(data.original_source, best.candidate.source)} />
        </Panel>
      )}

      {cfg.instructions && (
        <div className="mt-6 rounded-[7px] border border-rule bg-surface px-4 py-3 text-[13px]">
          <span className="eyebrow mr-2">User guidance</span>
          <span className="text-muted">{cfg.instructions}</span>
          <Pill tone="accent" className="ml-2">screened</Pill>
        </div>
      )}

      <FrameworkLog events={events} guardrails={data.state?.guardrail_events ?? []} />

      {data.state && <UsageTables state={data.state} />}
    </>
  );
}

function Checklist({ a }: { a: Attempt }) {
  const c = a.compare!;
  const t = a.tests;
  const cases = t ? Object.entries(t.details) : [];
  const items: [string, boolean | null, string][] = [
    ["Compiles", a.build?.ok ?? true, (a.build?.flags ?? a.candidate?.flags ?? []).join(" ")],
    ["Matches reference output", t ? cases.every(([, d]) => d.matched) : null, t ? `${cases.filter(([, d]) => d.matched).length}/${cases.length} inputs` : ""],
    ["ASan + UBSan clean", t?.sanitizer_ok ?? null, t?.sanitizer_ok == null ? "not run" : "small inputs"],
    ["Speedup ≥ 1.05×", c.speedup >= 1.05, fmtSpeedup(c.speedup)],
    ["Significant (Mann-Whitney)", c.p_value < 0.05, `p = ${c.p_value < 0.0001 ? c.p_value.toExponential(1) : c.p_value.toFixed(4)}`],
  ];
  return (
    <ul className="flex flex-col">
      {items.map(([label, ok, detail]) => (
        <li key={label} className="flex items-center gap-3 border-b border-rule py-[7px] last:border-b-0">
          <span className={cx("flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[11px]", ok === null ? "bg-sunken text-faint" : ok ? "bg-accent-soft text-accent" : "bg-bad-soft text-bad")}>
            {ok === null ? "–" : ok ? "✓" : "✕"}
          </span>
          <span className="flex-1">{label}</span>
          <span className="num text-[12px] text-muted">{detail}</span>
        </li>
      ))}
    </ul>
  );
}

function AttemptCard({ a, isBest }: { a: Attempt; isBest: boolean }) {
  const [showDiff, setShowDiff] = useState(isBest);
  const v = a.verdict;
  const strategies = a.plan?.strategies ?? [];
  return (
    <section className={cx("rounded-[7px] border bg-surface", isBest ? "border-accent/50" : "border-rule")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-rule px-4 py-3">
        <span className="font-mono text-[11px] text-faint">A{a.attempt}</span>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {strategies.length ? strategies.map((s, i) => (
            <span key={i} className="font-medium">{s.name}{s.target ? <span className="font-normal text-muted"> @ {s.target}</span> : null}{i < strategies.length - 1 && <span className="text-faint"> +</span>}</span>
          )) : <span className="text-muted">{v ? (REASON_LABEL[v.reason] ?? v.reason) : "planning…"}</span>}
          {a.plan?.flags && <span className="font-mono text-[11.5px] text-muted">[{a.plan.flags.join(" ")}]</span>}
        </div>
        {isBest && <Pill tone="accent">best</Pill>}
        {v ? <VerdictPill reason={v.reason} accepted={v.accepted} /> : <StatusPill status="running" />}
        {a.compare && <span className={cx("num text-[14px]", v?.accepted ? "text-accent" : "text-muted")}>{fmtSpeedup(a.compare.speedup)}</span>}
      </div>
      <div className="grid grid-cols-1 gap-5 p-4 lg:grid-cols-[1fr_1fr]">
        <div className="flex min-w-0 flex-col gap-3">
          {strategies.map((s, i) => (
            <div key={i}>
              <div className="flex items-center gap-2 text-[12px]">
                <span className="font-mono">{s.name}</span>
                <span className="h-[4px] w-16 overflow-hidden rounded-full bg-sunken"><span className="block h-full bg-ink/50" style={{ width: `${s.confidence * 100}%` }} /></span>
                <span className="num text-faint">{Math.round(s.confidence * 100)}%</span>
              </div>
              {s.rationale && <p className="mt-0.5 text-[12.5px] text-muted">{s.rationale}</p>}
            </div>
          ))}
          {v && !v.accepted && v.feedback_for_strategist && (
            <div className="rounded-[6px] border border-rule bg-sunken px-3 py-2 text-[12.5px]">
              <div className="eyebrow mb-1">Feedback to the Strategist</div>
              <p className="whitespace-pre-wrap break-words font-mono text-[11.5px] text-muted">{v.feedback_for_strategist.slice(0, 900)}</p>
            </div>
          )}
          {a.candidate?.repaired ? <Pill tone="warn">compile error self-repaired ×{a.candidate.repaired}</Pill> : null}
          {a.build?.dropped_flags?.length ? <p className="text-[12px] text-warn">Dropped flags: <span className="font-mono">{a.build.dropped_flags.join(" ")}</span></p> : null}
        </div>
        <div className="flex min-w-0 flex-col gap-3">
          {a.tests && (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(a.tests.details).map(([k, d]: [string, any]) => (
                <Pill key={k} tone={d.matched ? "accent" : "bad"} title={d.matched ? "" : `got ${d.actual_head} expected ${d.expected_head}`}>{k.split("/").pop()} {d.matched ? "✓" : d.status}</Pill>
              ))}
              {a.tests.sanitizer_ok != null && <Pill tone={a.tests.sanitizer_ok ? "accent" : "bad"}>sanitizers {a.tests.sanitizer_ok ? "✓" : "✕"}</Pill>}
            </div>
          )}
          {a.build && !a.build.ok && <pre className="max-h-40 overflow-auto rounded-[6px] bg-sunken p-2 font-mono text-[11px] text-bad">{a.build.stderr.slice(-1200)}</pre>}
          {a.compare?.baseline && a.compare.candidate && (
            <div>
              <StripPlot baseline={a.compare.baseline} candidate={a.compare.candidate} />
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted">
                <span>base {fmtMs(a.compare.baseline.median_ms)} (cv {fmtPct(a.compare.baseline.cv)})</span>
                <span>cand {fmtMs(a.compare.candidate.median_ms)} (cv {fmtPct(a.compare.candidate.cv)})</span>
                <span>cpu {fmtSpeedup(a.compare.cpu_speedup)}</span>
                <span>n={a.compare.candidate.runtimes_ms.length}</span>
              </div>
            </div>
          )}
        </div>
      </div>
      {a.candidate?.diff !== undefined && (
        <div className="border-t border-rule px-4 py-3">
          <button onClick={() => setShowDiff((s) => !s)} className="text-[12px] text-muted hover:text-ink">
            {showDiff ? "Hide" : "Show"} change in this attempt
          </button>
          {showDiff && <div className="mt-3"><DiffView diff={a.candidate.diff} maxHeight={420} /></div>}
        </div>
      )}
    </section>
  );
}

function FrameworkLog({ events, guardrails }: { events: RunEvent[]; guardrails: { agent: string; attempt: number | null; stage: string; detail: string }[] }) {
  const [open, setOpen] = useState(false);
  const fw = events.filter((e) => e.type === "agent_event");
  const a2a = events.filter((e) => e.type === "step_end" && e.agent === "critic" && e.data?.a2a);
  if (!fw.length && !guardrails.length && !a2a.length) return null;
  return (
    <Panel
      className="mt-6"
      eyebrow="Monitoring"
      title="Guardrails, A2A and framework callbacks"
      right={<button onClick={() => setOpen((o) => !o)} className="text-[12px] text-muted hover:text-ink">{open ? "Hide" : "Show"} {fw.length} callback events</button>}
    >
      <div className="flex flex-col gap-3 text-[12.5px]">
        <div className="flex flex-wrap gap-2">
          <Pill tone={guardrails.length ? "warn" : "accent"}>{guardrails.length} guardrail flag{guardrails.length === 1 ? "" : "s"}</Pill>
          {a2a.length > 0 && <Pill tone="info">{a2a.length} A2A call{a2a.length === 1 ? "" : "s"} to the ADK reviewer</Pill>}
          <Pill tone="outline">{fw.filter((e) => e.kind === "crewai_task_done").length} CrewAI task callbacks</Pill>
          <Pill tone="outline">{fw.filter((e) => e.kind === "crewai_step").length} CrewAI step callbacks</Pill>
        </div>
        {guardrails.map((g, i) => (
          <div key={i} className="rounded-[6px] border border-warn/30 bg-warn-soft px-3 py-2">
            <span className="font-mono text-[11.5px]">{g.agent}{g.attempt ? ` · A${g.attempt}` : ""} · {g.stage}</span>
            <div className="mt-0.5 break-words text-muted">{g.detail}</div>
          </div>
        ))}
        {a2a.map((e, i) => (
          <div key={i} className="font-mono text-[11.5px] text-muted">
            A{e.attempt} critic → {e.data.a2a.agent ?? "reviewer"} via {e.data.a2a.transport ?? "a2a"}
            {e.data.a2a.latency_ms ? ` · ${fmtMs(e.data.a2a.latency_ms)}` : ""}{e.data.a2a.error ? ` · error: ${e.data.a2a.error}` : ""}
          </div>
        ))}
        {open && (
          <div className="max-h-80 overflow-auto rounded-[6px] border border-rule bg-sunken p-2 font-mono text-[11px]">
            {fw.map((e, i) => (
              <div key={i} className="border-b border-rule/60 py-1 last:border-b-0">
                <span className="text-faint">{new Date(e.t * 1000).toLocaleTimeString()} </span>
                <span>{AGENT_LABEL[e.agent ?? ""] ?? e.agent}{e.attempt ? ` A${e.attempt}` : ""} </span>
                <span className={cx(e.kind === "guardrail" ? (e.ok ? "text-accent" : "text-warn") : "text-info")}>{e.kind}{e.step_type ? `:${e.step_type}` : ""}{e.stage ? `:${e.stage}` : ""} </span>
                <span className="text-muted">{(e.detail || e.preview || e.thought || e.tool || "").toString().slice(0, 160)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function UsageTables({ state }: { state: NonNullable<RunDetail["state"]> }) {
  const rows = Object.entries(state.usage_by_agent);
  const ms = state.messaging_stats ?? {};
  return (
    <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1.4fr_1fr]">
      <div>
        <div className="eyebrow mb-3">LLM usage by agent</div>
        {rows.length ? (
          <TableWrap>
            <thead><tr><Th>Agent</Th><Th right>Tokens in</Th><Th right>Tokens out</Th><Th right>Cost</Th></tr></thead>
            <tbody>
              {rows.map(([agent, u]) => (
                <tr key={agent}>
                  <Td><span className="flex items-center gap-2"><span className="inline-block h-[8px] w-[8px] rounded-[2px]" style={{ background: laneColor(agent) }} />{AGENT_LABEL[agent] ?? agent}</span></Td>
                  <Td right mono>{fmtTokens(u.prompt_tokens)}</Td>
                  <Td right mono>{fmtTokens(u.completion_tokens)}</Td>
                  <Td right mono>{fmtUsd(u.cost_usd)}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        ) : <Empty title="No LLM calls">This run used no language model.</Empty>}
      </div>
      <div>
        <div className="eyebrow mb-3">Messaging</div>
        <div className="rounded-[7px] border border-rule bg-surface px-4 py-1">
          <KV k="Mechanism" v={ms.mechanism ?? "—"} />
          <KV k="Messages" v={ms.messages ?? "—"} />
          <KV k="Deliveries" v={ms.deliveries ?? "—"} />
          <KV k="Payload bytes" v={ms.bytes ? Number(ms.bytes).toLocaleString() : "—"} />
          <KV k="Reads" v={ms.reads ?? "—"} />
          {ms.manager_fallbacks !== undefined && <KV k="Manager fallbacks" v={ms.manager_fallbacks} />}
          {ms.events_dispatched !== undefined && <KV k="Events dispatched" v={ms.events_dispatched} />}
        </div>
      </div>
    </div>
  );
}

function attemptsFromEvents(events: RunEvent[]): Attempt[] {
  const map = new Map<number, Attempt>();
  const get = (n: number) => {
    if (!map.has(n)) map.set(n, { attempt: n, plan: null, candidate: null, build: null, tests: null, compare: null, verdict: undefined as any });
    return map.get(n)!;
  };
  for (const e of events) {
    if (e.attempt == null) continue;
    const a = get(e.attempt);
    if (e.type === "step_end" && e.data) {
      if (e.agent === "strategist" && e.data.plan) a.plan = e.data.plan;
      if (e.agent === "transformer") a.candidate = { source: "", flags: e.data.flags ?? [], diff: e.data.diff ?? "", repaired: 0 };
      if (e.agent === "compiler_exec") {
        a.build = { ok: e.data.ok, stderr: e.data.stderr ?? "", flags: [], dropped_flags: e.data.dropped_flags ?? [] };
        a.tests = e.data.tests;
        if (a.candidate) a.candidate.repaired = e.data.repaired ?? 0;
      }
      if (e.agent === "benchmark") a.compare = e.data;
    }
    if (e.type === "attempt_end" && e.verdict) a.verdict = e.verdict;
  }
  return Array.from(map.values()).sort((x, y) => x.attempt - y.attempt);
}

function sumUsage(events: RunEvent[]) {
  return events.filter((e) => e.type === "step_end").reduce(
    (u, e) => ({ prompt_tokens: u.prompt_tokens + (e.tokens_in ?? 0), completion_tokens: u.completion_tokens + (e.tokens_out ?? 0), calls: u.calls + ((e.tokens_in ?? 0) > 0 ? 1 : 0), cost_usd: u.cost_usd + (e.cost_usd ?? 0) }),
    { prompt_tokens: 0, completion_tokens: 0, calls: 0, cost_usd: 0 },
  );
}
