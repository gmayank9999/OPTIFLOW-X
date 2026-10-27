"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { RunRow, useApi } from "@/lib/api";
import { fmtAgo, fmtSpeedup, fmtTokens, fmtUsd, num, STOP_LABEL } from "@/lib/format";
import { Empty, ErrorNote, PageHeader, Pill, Segmented, Skeleton, StatusPill, TableWrap, Td, Th } from "@/components/ui";

export default function RunsPage() {
  const { data, error } = useApi<RunRow[]>("/runs?limit=1000", 5000);
  const [experiment, setExperiment] = useState("all");
  const [variant, setVariant] = useState("all");
  const [q, setQ] = useState("");

  const experiments = useMemo(() => ["all", ...Array.from(new Set((data ?? []).map((r) => r.experiment ?? "dashboard")))], [data]);
  const rows = (data ?? []).filter(
    (r) =>
      (experiment === "all" || (r.experiment ?? "dashboard") === experiment) &&
      (variant === "all" || (variant === "llm" ? !["flags_only", "rule_only"].includes(r.variant) : r.variant === variant)) &&
      (!q || r.program_id.includes(q)),
  );

  return (
    <>
      <PageHeader eyebrow="Runs" title="Every optimization run">
        One row per run, newest first. Speedups are the best accepted candidate against the -O2 baseline, measured
        interleaved in the same container session.
      </PageHeader>
      {error && <div className="mb-4"><ErrorNote error={error} /></div>}

      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          <Segmented size="sm" value={variant} onChange={setVariant} options={[
            { value: "all", label: "All" }, { value: "llm", label: "LLM agents" },
            { value: "flags_only", label: "Flags only" }, { value: "rule_only", label: "Rule-based" },
          ]} />
          {experiments.length > 2 && (
            <select value={experiment} onChange={(e) => setExperiment(e.target.value)} className="rounded-[6px] border border-rule bg-surface px-2 py-[3px] font-mono text-[12px]">
              {experiments.map((e) => <option key={e} value={e}>{e === "all" ? "all experiments" : e}</option>)}
            </select>
          )}
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by program…" className="w-full rounded-[6px] border border-rule bg-surface px-3 py-[6px] text-[13px] outline-none focus:border-ink/40 lg:w-64" />
      </div>

      {!data ? (
        <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10" />)}</div>
      ) : rows.length === 0 ? (
        <Empty title="No runs match">Start a run from the Overview page or run an experiment config.</Empty>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>Program</Th><Th>Configuration</Th><Th>Status</Th><Th right>Speedup</Th><Th right>Attempts</Th>
              <Th right>Tokens</Th><Th right>Cost</Th><Th right>Wall</Th><Th>Stopped</Th><Th right>When</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const sp = num(r.speedup);
              return (
                <tr key={r.run_id} className="hover:bg-sunken/50">
                  <Td><Link href={`/run/?id=${r.run_id}`} className="font-mono text-[12.5px] hover:underline">{r.program_id}</Link></Td>
                  <Td>
                    {["flags_only", "rule_only"].includes(r.variant) ? (
                      <Pill tone="outline">{r.variant.replace("_", " ")}</Pill>
                    ) : (
                      <span className="text-[12px] text-muted">
                        {r.architecture} · {r.messaging} · {r.prompt_style}
                        {r.variant !== "full" && <> · <span className="text-warn">{r.variant}</span></>}
                      </span>
                    )}
                  </Td>
                  <Td><StatusPill status={r.status} /></Td>
                  <Td right mono className={sp && sp >= 1.05 ? "font-medium text-accent" : "text-muted"}>{r.status === "done" ? fmtSpeedup(sp) : "—"}</Td>
                  <Td right mono>{r.attempts ?? "—"}</Td>
                  <Td right mono>{fmtTokens(r.total_tokens)}</Td>
                  <Td right mono>{fmtUsd(r.cost_usd)}</Td>
                  <Td right mono>{r.latency_s ? `${Number(r.latency_s).toFixed(0)}s` : "—"}</Td>
                  <Td className="text-[12px] text-muted">{r.error ? <span className="text-bad">error</span> : STOP_LABEL[r.stop_reason ?? ""] ?? r.stop_reason ?? ""}</Td>
                  <Td right className="text-[12px] text-faint">{fmtAgo(r.started_at)}</Td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
    </>
  );
}
