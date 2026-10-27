"use client";

import { useApi } from "@/lib/api";
import { cx, fmtPct } from "@/lib/format";
import { Empty, ErrorNote, PageHeader, Panel, Pill, Skeleton, Stat, StatRow, TableWrap, Td, Th } from "@/components/ui";

type StrategyInfo = {
  n_labeled: number; n_positive: number; model_auc: number | null; heuristic_auc: number | null;
  backend: "model" | "heuristic"; why: string; feature_importance?: Record<string, number>;
};
type MlResponse = {
  report: null | {
    n_programs: number; n_labels: number; n_positive_labels: number; label_sources: { sweep: number; agent: number };
    per_strategy: Record<string, StrategyInfo>;
    ranking: Record<string, number | null>;
  };
  backends: Record<string, string>;
  dataset: Record<string, string>[];
};

const STRATEGIES = ["flags", "interchange", "tiling", "vectorize", "unroll", "fusion", "fission", "soa", "hoist", "memoize", "algorithmic"];

export default function PredictorPage() {
  const { data, error } = useApi<MlResponse>("/ml");
  const r = data?.report;
  const rk = r?.ranking ?? {};
  return (
    <>
      <PageHeader eyebrow="Strategy predictor" title="A ranking prior, held to account">
        Per-strategy XGBoost classifiers trained on a no-LLM sweep (flag variants plus hand-written single-strategy rewrites,
        each verified against the reference outputs) and on the agents&apos; own judged attempts. Untested strategies are left
        unlabeled, not counted as failures. A strategy uses its model only if it beat the static heuristic on held-out programs.
      </PageHeader>
      {error && <ErrorNote error={error} />}
      {!data ? <Skeleton className="h-80" /> : !r ? (
        <Empty title="No trained model yet">Run <span className="font-mono">python -m optiflow.ml.run_sweep</span> then <span className="font-mono">python -m optiflow.ml.train_xgb</span>.</Empty>
      ) : (
        <>
          <StatRow>
            <Stat label="Labels" value={r.n_labels} sub={`${r.label_sources.sweep} sweep · ${r.label_sources.agent} from agent runs`} />
            <Stat label="Positive labels" value={r.n_positive_labels} sub="verified ≥ 1.10×, p < 0.05" />
            <Stat label="Top-1 hit · hybrid" value={fmtPct(rk.hybrid_top1, 0)} tone="accent" sub={`heuristic ${fmtPct(rk.heuristic_top1, 0)} · naive ${fmtPct(rk.naive_top1, 0)}`} />
            <Stat label="Top-3 hit · hybrid" value={fmtPct(rk.hybrid_top3, 0)} tone="accent" sub={`heuristic ${fmtPct(rk.heuristic_top3, 0)} · naive ${fmtPct(rk.naive_top3, 0)}`} />
            <Stat label="Strategies on a model" value={`${Object.values(data.backends).filter((b) => b === "model").length}/${STRATEGIES.length}`} sub="rest use the heuristic" />
          </StatRow>

          <div className="mt-6">
            <TableWrap>
              <thead>
                <tr><Th>Strategy</Th><Th right>Labeled</Th><Th right>Positive</Th><Th>Heuristic AUC</Th><Th>Model AUC (LOPO)</Th><Th>Used</Th><Th>Why</Th></tr>
              </thead>
              <tbody>
                {STRATEGIES.map((s) => {
                  const info = r.per_strategy[s];
                  if (!info) return null;
                  return (
                    <tr key={s}>
                      <Td mono>{s}</Td>
                      <Td right mono>{info.n_labeled}</Td>
                      <Td right mono>{info.n_positive}</Td>
                      <Td><Auc v={info.heuristic_auc} /></Td>
                      <Td><Auc v={info.model_auc} /></Td>
                      <Td><Pill tone={info.backend === "model" ? "accent" : "neutral"}>{info.backend}</Pill></Td>
                      <Td className="text-[12px] text-muted">{info.why}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </TableWrap>
            <p className="mt-2 text-[11.5px] text-faint">AUC on held-out programs (leave-one-program-out). 0.5 is chance; the dashed tick marks it.</p>
          </div>

          <Panel className="mt-6" eyebrow="Coverage" title="What the dataset actually knows" pad={false}>
            <LabelMatrix rows={data.dataset} />
          </Panel>
        </>
      )}
    </>
  );
}

function Auc({ v }: { v: number | null }) {
  if (v === null || v === undefined) return <span className="text-faint">n/a</span>;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-[8px] w-24 rounded-full bg-sunken">
        <div className="absolute inset-y-0 border-l border-dashed border-faint" style={{ left: "50%" }} />
        <div className={cx("absolute inset-y-0 left-0 rounded-full", v >= 0.6 ? "bg-accent" : v >= 0.5 ? "bg-faint" : "bg-bad/70")} style={{ width: `${v * 100}%` }} />
      </div>
      <span className="num text-[12px]">{v.toFixed(2)}</span>
    </div>
  );
}

function LabelMatrix({ rows }: { rows: Record<string, string>[] }) {
  return (
    <div className="overflow-x-auto p-4">
      <table className="border-collapse">
        <thead>
          <tr>
            <th />
            {STRATEGIES.map((s) => (
              <th key={s} className="h-20 w-7 align-bottom">
                <div className="mx-auto w-4 origin-bottom-left translate-x-3 -rotate-[55deg] whitespace-nowrap font-mono text-[10px] font-normal text-muted">{s}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.program_id}>
              <td className="pr-3 font-mono text-[11px] text-muted">{row.program_id}</td>
              {STRATEGIES.map((s) => {
                const y = row[`y_${s}`];
                const sp = row[`s_${s}`];
                const src = row[`src_${s}`];
                const tone = y === "1" ? "bg-accent" : y === "0" ? "bg-faint/50" : "";
                return (
                  <td key={s} className="p-[2px]">
                    <div title={y === "" || y === undefined ? "untested" : `${y === "1" ? "positive" : "negative"}${sp ? ` · ${Number(sp).toFixed(2)}×` : ""} · ${src}`}
                      className={cx("mx-auto h-[14px] w-[22px] rounded-[2px]", tone || "border border-dashed border-rule", src === "agent" && "ring-1 ring-info")} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap gap-4 text-[11.5px] text-muted">
        <span className="flex items-center gap-1.5"><span className="inline-block h-[10px] w-[16px] rounded-[2px] bg-accent" />verified ≥ 1.10×</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-[10px] w-[16px] rounded-[2px] bg-faint/50" />tested, no gain</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-[10px] w-[16px] rounded-[2px] border border-dashed border-rule" />never tested</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-[10px] w-[16px] rounded-[2px] ring-1 ring-info" />label from an agent run</span>
      </div>
    </div>
  );
}
