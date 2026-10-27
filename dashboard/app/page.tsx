"use client";

import Link from "next/link";
import { ProgramRow, RunRow, useApi } from "@/lib/api";
import { AGENT_LABEL, fmtAgo, fmtSpeedup, fmtUsd, geomean, laneColor, num } from "@/lib/format";
import { SpeedupChart } from "@/components/SpeedupChart";
import { StartRun } from "@/components/StartRun";
import { Empty, ErrorNote, PageHeader, Panel, Pill, Skeleton, Stat, StatRow, StatusPill } from "@/components/ui";

const PIPELINE = [
  ["analyzer", "Parse loops & features (tree-sitter)"],
  ["profiler", "perf counters + loop hotspots"],
  ["strategist", "Plan from profile, RAG, predictor"],
  ["transformer", "Rewrite the source"],
  ["compiler_exec", "Compile, test, ASan/UBSan"],
  ["benchmark", "Interleaved timing, Mann-Whitney"],
  ["critic", "Rules decide; CrewAI or ADK (A2A) explains"],
] as const;

export default function Overview() {
  const { data: programs, error } = useApi<ProgramRow[]>("/programs", 15000);
  const { data: runs } = useApi<RunRow[]>("/runs?limit=8", 5000);

  const agentBest = programs?.map((p) => num(p.best_speedup)).filter((v): v is number => v !== null) ?? [];
  const flagsBest = programs?.map((p) => num(p.flags_speedup)).filter((v): v is number => v !== null) ?? [];
  const both = programs?.filter((p) => num(p.best_speedup) !== null && num(p.flags_speedup) !== null) ?? [];
  const beatFlags = both.filter((p) => (num(p.best_speedup) ?? 0) > (num(p.flags_speedup) ?? 0) * 1.05).length;
  const totalRuns = programs?.reduce((a, p) => a + (p.runs ?? 0), 0) ?? 0;

  return (
    <>
      <PageHeader eyebrow="Overview" title="Measurement-driven optimization of C programs">
        Seven agents propose source- and flag-level changes; nothing is accepted until it compiles, matches the
        reference output on every input, survives the sanitizers, and is faster under a significance test.
      </PageHeader>

      {error && <div className="mb-6"><ErrorNote error={error} /></div>}

      <StatRow>
        <Stat label="Programs" value={programs ? programs.length : "—"} sub="7 categories · 3 inputs each" />
        <Stat label="Runs recorded" value={programs ? totalRuns : "—"} sub="results/runs.csv" />
        <Stat label="Agents · geo-mean" value={agentBest.length ? fmtSpeedup(geomean(agentBest)) : "—"} tone="accent" sub={`${agentBest.length} programs with an agent run`} />
        <Stat label="-O3 only · geo-mean" value={flagsBest.length ? fmtSpeedup(geomean(flagsBest)) : "—"} sub={`${flagsBest.length} programs measured`} />
        <Stat label="Agents beat -O3" value={both.length ? `${beatFlags}/${both.length}` : "—"} sub="by more than 5%" />
      </StatRow>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:items-start">
        <Panel eyebrow="Start" title="New optimization run">
          <StartRun />
        </Panel>
        <Panel eyebrow="Latest" title="Recent runs" right={<Link href="/runs/" className="text-[12px] text-muted hover:text-ink">All runs →</Link>} pad={false}>
          {!runs ? (
            <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9" />)}</div>
          ) : runs.length === 0 ? (
            <div className="p-4"><Empty title="No runs yet">Start one on the left, or run the baselines with <span className="font-mono">run_matrix e0_baselines.yaml</span>.</Empty></div>
          ) : (
            <ul>
              {runs.map((r) => (
                <li key={r.run_id} className="border-b border-rule last:border-b-0">
                  <Link href={`/run/?id=${r.run_id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-sunken/60">
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-mono text-[12.5px]">{r.program_id}</div>
                      <div className="truncate text-[11.5px] text-muted">
                        {r.variant === "full" ? `${r.architecture} · ${r.messaging} · ${r.prompt_style}` : r.variant.replace("_", " ")}
                      </div>
                    </div>
                    {r.status === "done" ? <span className="num text-[13px]">{fmtSpeedup(r.speedup)}</span> : <StatusPill status={r.status} />}
                    <span className="w-16 text-right text-[11.5px] text-faint">{fmtAgo(r.started_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel className="mt-6" eyebrow="One attempt" title="What happens in every attempt">
        <ol className="grid grid-cols-1 gap-px overflow-hidden rounded-[6px] border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-7">
          {PIPELINE.map(([agent, text], i) => (
            <li key={agent} className="bg-surface px-3 py-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="inline-block h-[8px] w-[8px] rounded-[2px]" style={{ background: laneColor(agent) }} />
                <span className="font-mono text-[10.5px] text-faint">{i + 1}</span>
              </div>
              <div className="text-[12.5px] font-medium">{AGENT_LABEL[agent]}</div>
              <div className="mt-0.5 text-[11.5px] leading-snug text-muted">{text}</div>
            </li>
          ))}
        </ol>
        <div className="mt-3 flex flex-wrap gap-2 text-[11.5px] text-muted">
          <Pill tone="outline">rejects → feedback to the Strategist</Pill>
          <Pill tone="outline">accepts stack: the next attempt builds on the best</Pill>
          <Pill tone="outline">stop: budget · cost cap · diminishing returns · 3 rejects</Pill>
        </div>
      </Panel>

      <Panel className="mt-6" eyebrow="Results" title="Speedup by program" right={<Link href="/programs/" className="text-[12px] text-muted hover:text-ink">All programs →</Link>}>
        {programs && programs.some((p) => p.best_speedup || p.flags_speedup) ? (
          <SpeedupChart programs={programs} />
        ) : (
          <Empty title="No measured programs yet">Run the LLM-free baselines first: <span className="font-mono">python -m optiflow.experiments.run_matrix optiflow/experiments/configs/e0_baselines.yaml</span></Empty>
        )}
      </Panel>
    </>
  );
}
