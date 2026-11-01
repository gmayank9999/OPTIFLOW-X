"use client";

import { useApi } from "@/lib/api";
import { CATEGORY_LABEL, cx, fmtPct, fmtSpeedup, fmtTokens, fmtUsd } from "@/lib/format";
import { Empty, ErrorNote, PageHeader, Panel, Pill, Skeleton, Stat, StatRow, TableWrap, Td, Th } from "@/components/ui";

type Summary = Record<string, any> & {
  runs: number; programs: number; geomean_speedup: number | null; median_speedup: number; success_rate: number;
  success_ci: [number | null, number | null]; mean_cost_usd: number; mean_latency_s: number; p95_latency_s: number;
  mean_tokens: number; mean_attempts: number; mean_messages: number; mean_deliveries: number; mean_message_bytes: number;
};
type Analysis = {
  runs: number; programs?: number; overall_geomean_speedup?: number; total_cost_usd?: number;
  experiments?: Record<string, { runs: number; varied: string[]; summaries: Record<string, Summary[]>; tests: Record<string, any> }>;
  by_category?: Summary[];
  pareto?: { config: string; success_rate: number; mean_cost_usd: number; runs: number; geomean_speedup: number | null; pareto: boolean }[];
};

const EXP_TITLE: Record<string, string> = {
  e0_baselines: "E0 · LLM-free baselines",
  e1_architecture: "E1 · Architecture",
  e2_messaging: "E2 · Messaging",
  e3_prompting: "E3 · Prompting style",
  e4_models: "E4 · Model assignment",
  e5_ablations: "E5 · Ablations",
  e6_interop: "E6 · CrewAI vs ADK over A2A (critic)",
  e7_repeats: "E7 · Architecture, 3 repeats per cell",
  dashboard: "One-off runs from the dashboard",
  cli: "One-off runs from the command line",
  smoke: "Smoke tests",
};

// Not designed experiments: rows differ in program and configuration at
// once, so they get a summary but are never compared with each other.
const ADHOC = new Set(["dashboard", "cli", "smoke", "adhoc"]);

export default function ExperimentsPage() {
  const { data, error } = useApi<Analysis>("/experiments/summary", 30000);
  return (
    <>
      <PageHeader eyebrow="Experiments" title="Comparisons, with the statistics attached">
        Speedups are averaged geometrically. Success is best speedup ≥ 1.05× with all tests passing, shown with a 95% Wilson
        interval. Configurations measured on the same programs are compared with a Friedman test and Holm-corrected Wilcoxon
        signed-rank tests on log-speedups.
      </PageHeader>
      {error && <ErrorNote error={error} />}
      {!data ? <Skeleton className="h-80" /> : data.runs === 0 ? (
        <Empty title="No experiment runs yet">
          Run a config, e.g. <span className="font-mono">python -m optiflow.experiments.run_matrix optiflow/experiments/configs/e0_baselines.yaml</span>
        </Empty>
      ) : (
        <>
          <StatRow>
            <Stat label="Runs analysed" value={data.runs} />
            <Stat label="Programs covered" value={data.programs ?? "—"} />
            <Stat label="Geo-mean speedup" value={fmtSpeedup(data.overall_geomean_speedup)} sub="all runs, all configs" />
            <Stat label="Total LLM spend" value={fmtUsd(data.total_cost_usd)} />
            <Stat label="Experiments" value={Object.keys(data.experiments ?? {}).length} />
          </StatRow>

          {Object.entries(data.experiments ?? {}).map(([name, exp]) => (
            <Panel
              key={name}
              className="mt-6"
              eyebrow={`${exp.runs} run${exp.runs === 1 ? "" : "s"}${ADHOC.has(name) ? " · not a comparison" : ""}`}
              title={EXP_TITLE[name] ?? name}
            >
              {Object.entries(exp.summaries).map(([factor, rows]) => (
                <div key={factor} className="mb-5 last:mb-0">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="eyebrow">by {factor.replace("_", " ")}</span>
                    <TestBadge test={exp.tests?.[factor]} />
                  </div>
                  <SummaryTable rows={rows} factor={factor} />
                  <PairwiseTable test={exp.tests?.[factor]} />
                </div>
              ))}
            </Panel>
          ))}

          {data.pareto && data.pareto.length > 1 && (
            <Panel className="mt-6" eyebrow="Trade-off" title="Success rate vs cost per run">
              <Pareto points={data.pareto} />
            </Panel>
          )}

          {data.by_category && (
            <Panel className="mt-6" eyebrow="Breakdown" title="By program category (all runs)" pad={false}>
              <SummaryTable rows={data.by_category} factor="category" flush />
            </Panel>
          )}
        </>
      )}
    </>
  );
}

function SummaryTable({ rows, factor, flush }: { rows: Summary[]; factor: string; flush?: boolean }) {
  const best = Math.max(...rows.map((r) => r.geomean_speedup ?? 0));
  const table = (
    <table className="w-full border-collapse text-[13px]">
      <thead>
        <tr>
          <Th>{factor.replace("_", " ")}</Th><Th right>Runs</Th><Th right>Geo-mean</Th><Th right>Median</Th>
          <Th>Success (95% CI)</Th><Th right>Cost / run</Th><Th right>Latency</Th><Th right>Tokens</Th><Th right>Msgs / deliveries</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={String(r[factor])}>
            <Td className="font-medium">{factor === "category" ? CATEGORY_LABEL[r[factor]] ?? r[factor] : r[factor]}</Td>
            <Td right mono>{r.runs}</Td>
            <Td right mono className={cx(r.geomean_speedup === best && rows.length > 1 && "font-medium text-accent")}>{fmtSpeedup(r.geomean_speedup)}</Td>
            <Td right mono className="text-muted">{fmtSpeedup(r.median_speedup)}</Td>
            <Td><CiBar rate={r.success_rate} ci={r.success_ci} /></Td>
            <Td right mono>{fmtUsd(r.mean_cost_usd)}</Td>
            <Td right mono>{r.mean_latency_s ? `${r.mean_latency_s.toFixed(0)}s` : "—"}</Td>
            <Td right mono>{fmtTokens(r.mean_tokens)}</Td>
            <Td right mono className="text-muted">{r.mean_messages ? `${r.mean_messages.toFixed(0)} / ${r.mean_deliveries.toFixed(0)}` : "—"}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return flush ? <div className="overflow-x-auto">{table}</div> : <div className="overflow-x-auto rounded-[6px] border border-rule [&_tr:last-child_td]:border-b-0">{table}</div>;
}

function CiBar({ rate, ci }: { rate: number; ci: [number | null, number | null] }) {
  const [lo, hi] = ci;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-[12px] w-28 rounded-[2px] bg-sunken">
        {lo !== null && hi !== null && <div className="absolute inset-y-[4px] rounded-full bg-accent/30" style={{ left: `${lo * 100}%`, width: `${(hi - lo) * 100}%` }} />}
        <div className="absolute inset-y-0 w-[2px] bg-accent" style={{ left: `calc(${rate * 100}% - 1px)` }} />
      </div>
      <span className="num text-[12px]">{fmtPct(rate, 0)}</span>
    </div>
  );
}

function TestBadge({ test }: { test: any }) {
  if (!test) return null;
  if (test.note) return <span className="text-[11.5px] text-faint">{test.note}</span>;
  if (test.friedman) {
    const p = test.friedman.p_value;
    return <Pill tone={p < 0.05 ? "accent" : "neutral"}>Friedman p = {p < 0.001 ? p.toExponential(1) : p.toFixed(3)} · {test.paired_programs} paired programs</Pill>;
  }
  return <Pill>{test.paired_programs} paired programs</Pill>;
}

function PairwiseTable({ test }: { test: any }) {
  if (!test?.pairwise?.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {test.pairwise.map((p: any) => (
        <Pill key={`${p.a}-${p.b}`} tone={p.significant ? "accent" : "outline"} title={`raw p = ${p.p_raw.toFixed(4)}`}>
          {p.a} vs {p.b}: ×{p.median_ratio.toFixed(2)} · p<sub>Holm</sub> {p.p_holm.toFixed(3)}
        </Pill>
      ))}
    </div>
  );
}

function Pareto({ points }: { points: NonNullable<Analysis["pareto"]> }) {
  const W = 640, H = 260, L = 48, B = 34, T = 12, R = 16;
  const maxC = Math.max(1e-4, ...points.map((p) => p.mean_cost_usd)) * 1.1;
  const sx = (c: number) => L + (c / maxC) * (W - L - R);
  const sy = (s: number) => T + (1 - s) * (H - T - B);
  const front = points.filter((p) => p.pareto).sort((a, b) => a.mean_cost_usd - b.mean_cost_usd);
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[520px] w-full">
        {[0, 0.25, 0.5, 0.75, 1].map((s) => (
          <g key={s}>
            <line x1={L} x2={W - R} y1={sy(s)} y2={sy(s)} style={{ stroke: "rgb(var(--rule))" }} />
            <text x={L - 8} y={sy(s) + 3} textAnchor="end" className="fill-faint font-mono" fontSize={10}>{Math.round(s * 100)}%</text>
          </g>
        ))}
        <text x={W - R} y={H - 6} textAnchor="end" className="fill-faint font-mono" fontSize={10}>mean cost per run → {fmtUsd(maxC)}</text>
        <polyline points={front.map((p) => `${sx(p.mean_cost_usd)},${sy(p.success_rate)}`).join(" ")} style={{ fill: "none", stroke: "rgb(var(--accent))", strokeDasharray: "3 3" }} />
        {points.map((p) => (
          <g key={p.config}>
            <circle cx={sx(p.mean_cost_usd)} cy={sy(p.success_rate)} r={p.pareto ? 5 : 3.5} style={{ fill: p.pareto ? "rgb(var(--accent))" : "rgb(var(--faint))" }}>
              <title>{`${p.config}\n${fmtPct(p.success_rate, 0)} success · ${fmtUsd(p.mean_cost_usd)} · ${fmtSpeedup(p.geomean_speedup)} geo-mean`}</title>
            </circle>
          </g>
        ))}
      </svg>
      <div className="mt-1 text-[11.5px] text-faint">Filled green: Pareto-optimal (no configuration is both cheaper and more successful). Hover a point for its configuration.</div>
    </div>
  );
}
