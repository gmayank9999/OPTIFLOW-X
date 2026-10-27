"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ProgramDetail, useApi } from "@/lib/api";
import { CATEGORY_LABEL, cx, fmtAgo, fmtInt, fmtMs, fmtPct, fmtSpeedup, num } from "@/lib/format";
import { SourceView } from "@/components/SourceView";
import { StartRun } from "@/components/StartRun";
import { Empty, ErrorNote, KV, PageHeader, Panel, Pill, Skeleton, Stat, StatRow, StatusPill, TableWrap, Td, Th } from "@/components/ui";

const FEATURE_LABEL: Record<string, string> = {
  stride_mismatch: "strided inner loop",
  has_recursion: "recursion",
  has_struct_array: "array of structs",
  strlen_in_loop_cond: "strlen in loop condition",
  pointer_chasing: "pointer chasing",
  uses_float: "floating point",
};

export default function ProgramPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40" />}>
      <ProgramView />
    </Suspense>
  );
}

function ProgramView() {
  const id = useSearchParams().get("id");
  const { data, error } = useApi<ProgramDetail>(id ? `/programs/${id}` : null);
  if (!id) return <Empty title="No program selected" />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return <div className="space-y-4"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  const p = data.profile;
  const flags = Object.entries(FEATURE_LABEL).filter(([k]) => data.features[k]);
  const sweep = data.sweep?.variants ?? [];

  return (
    <>
      <PageHeader
        eyebrow={`${CATEGORY_LABEL[data.meta.category] ?? data.meta.category} · ${data.meta.language.toUpperCase()}`}
        title={<span className="font-mono text-[24px] md:text-[28px]">{data.id}</span>}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone="outline">output compared {data.meta.compare === "exact" ? "exactly" : `within ${data.meta.tolerance}`}</Pill>
          <Pill tone="outline">bench input {data.meta.bench_input.split("/").pop()}</Pill>
          {data.meta.subset10 && <Pill tone="outline">10-program subset</Pill>}
          {flags.map(([k, label]) => <Pill key={k}>{label}</Pill>)}
        </div>
      </PageHeader>

      <StatRow>
        <Stat label="Baseline (-O2)" value={fmtMs(data.stability?.median_ms ?? p?.baseline_runtime_ms)} sub={data.stability ? `CV ${fmtPct(data.stability.cv_within_max)} within · ${fmtPct(data.stability.cv_across_sessions)} across sessions` : undefined} />
        <Stat label="IPC" value={p?.ipc?.toFixed(2) ?? "—"} sub={p ? `counters: ${p.counters_source}` : "not profiled yet"} />
        <Stat label="L1 miss rate" value={fmtPct(p?.l1_miss_rate)} tone={(p?.l1_miss_rate ?? 0) > 0.1 ? "warn" : undefined} />
        <Stat label="LLC miss rate" value={fmtPct(p?.llc_miss_rate)} />
        <Stat label="Branch misses" value={fmtPct(p?.branch_miss_rate, 2)} />
      </StatRow>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel eyebrow="Source" title={p?.hotspots?.length ? "Heat gutter: share of perf samples per loop" : "main.c"} pad={false}>
          <div className="p-3">
            <SourceView source={data.source} hotspots={p?.hotspots ?? []} loops={data.loops} maxHeight={640} />
          </div>
        </Panel>
        <div className="flex flex-col gap-6">
          <Panel eyebrow="Run" title="Optimize this program">
            <StartRun defaultProgram={data.id} compact />
          </Panel>
          {p && (
            <Panel eyebrow="Profile" title="Where the time goes">
              <p className="mb-3 text-[12.5px] text-muted">{p.bottleneck_text}</p>
              {p.hotspots.map((h, i) => (
                <div key={i} className="mb-2">
                  <div className="mb-1 flex justify-between text-[12px]">
                    <span className="font-mono">{h.function}() L{h.start_line}–{h.end_line}</span>
                    <span className="num">{h.time_pct.toFixed(1)}%</span>
                  </div>
                  <div className="h-[5px] overflow-hidden rounded-full bg-sunken"><div className="bar-grow h-full bg-accent" style={{ width: `${h.time_pct}%` }} /></div>
                </div>
              ))}
              <KV k="Peak memory" v={`${fmtInt(p.peak_mem_kb)} KB`} />
            </Panel>
          )}
          <Panel eyebrow="Inputs" title="Test oracle">
            {data.inputs.map((i) => (
              <div key={i.name} className="border-b border-rule py-2 last:border-b-0">
                <div className="flex justify-between text-[12px]">
                  <span className="font-mono">{i.name.split("/").pop()}{i.name === data.meta.bench_input && <span className="ml-2 text-accent">bench</span>}</span>
                  <span className="num text-muted">{i.bytes > 1024 ? `${(i.bytes / 1024).toFixed(0)} KB` : `${i.bytes} B`}</span>
                </div>
                <div className="mt-0.5 truncate font-mono text-[11px] text-faint">{i.head.split("\n")[0]}</div>
              </div>
            ))}
          </Panel>
        </div>
      </div>

      {sweep.length > 0 && (
        <div className="mt-8">
          <div className="eyebrow mb-3">Strategy sweep (no LLM): every variant benchmarked against -O2 in one interleaved session</div>
          <TableWrap>
            <thead><tr><Th>Variant</Th><Th>Strategy</Th><Th>Build</Th><Th right>Speedup</Th><Th right>CPU</Th><Th right>p</Th><Th>Label</Th></tr></thead>
            <tbody>
              {sweep.map((v) => (
                <tr key={v.name}>
                  <Td mono className="text-[12px]">{v.name}</Td>
                  <Td>{v.strategy}</Td>
                  <Td className="text-[12px] text-muted">{v.compiler} {v.flags.join(" ")}</Td>
                  <Td right mono className={cx(v.positive && "font-medium text-accent")}>{v.status === "measured" ? fmtSpeedup(v.speedup) : <span className="text-bad">{v.status}</span>}</Td>
                  <Td right mono className="text-muted">{fmtSpeedup(v.cpu_speedup)}</Td>
                  <Td right mono className="text-muted">{v.p_value !== undefined ? v.p_value.toExponential(1) : "—"}</Td>
                  <Td>{v.status === "measured" ? <Pill tone={v.positive ? "accent" : "neutral"}>{v.positive ? "≥ 1.10× ✓" : "negative"}</Pill> : "—"}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}

      <div className="mt-8">
        <div className="eyebrow mb-3">Runs on this program</div>
        {data.runs.length === 0 ? (
          <Empty title="Not optimized yet">Start a run above.</Empty>
        ) : (
          <TableWrap>
            <thead><tr><Th>Run</Th><Th>Configuration</Th><Th right>Speedup</Th><Th right>Attempts</Th><Th>Winning change</Th><Th right>When</Th></tr></thead>
            <tbody>
              {data.runs.map((r) => (
                <tr key={r.run_id} className="hover:bg-sunken/50">
                  <Td><Link href={`/run/?id=${r.run_id}`} className="font-mono text-[12px] hover:underline">{r.run_id.slice(0, 8)}</Link></Td>
                  <Td className="text-[12px] text-muted">{["flags_only", "rule_only"].includes(r.variant) ? r.variant.replace("_", " ") : `${r.architecture} · ${r.messaging} · ${r.prompt_style}`}</Td>
                  <Td right mono className={cx((num(r.speedup) ?? 0) >= 1.05 && "font-medium text-accent")}>{r.error ? <StatusPill status="failed" /> : fmtSpeedup(r.speedup)}</Td>
                  <Td right mono>{r.attempts}</Td>
                  <Td>{r.winning_strategy ? <Pill>{r.winning_strategy}</Pill> : <span className="text-faint">—</span>}</Td>
                  <Td right className="text-[12px] text-faint">{fmtAgo(r.started_at)}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </div>
    </>
  );
}
