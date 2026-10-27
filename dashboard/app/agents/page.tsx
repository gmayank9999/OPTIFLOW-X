"use client";

import { useState } from "react";
import { AgentMetric, useApi } from "@/lib/api";
import { AGENT_LABEL, fmtMs, fmtPct, fmtTokens, fmtUsd, laneColor } from "@/lib/format";
import { Empty, ErrorNote, PageHeader, Panel, Segmented, Skeleton, TableWrap, Td, Th } from "@/components/ui";

const ROLE: Record<string, string> = {
  analyzer: "MCP: get_program, static_analysis · LLM summary",
  profiler: "MCP: profile_program · LLM interpretation",
  manager: "LLM: picks the next action (hierarchical only)",
  strategist: "LLM: plan from profile, RAG, predictor",
  transformer: "LLM: rewrites source · no tools",
  compiler_exec: "MCP: compile_code, run_tests · LLM self-repair",
  benchmark: "MCP: compare_to_baseline · no LLM",
  critic: "Rules decide · LLM explains rejections",
};

export default function AgentsPage() {
  const [arch, setArch] = useState("all");
  const { data, error } = useApi<AgentMetric[]>(`/metrics/agents${arch === "all" ? "" : `?architecture=${arch}`}`, 15000);
  const maxP95 = Math.max(1, ...(data ?? []).map((a) => a.p95_ms));

  return (
    <>
      <PageHeader eyebrow="Agents" title="Latency, tokens and cost per agent">
        Computed from the OpenTelemetry spans of every recorded run. Critical-path share is the fraction of wall time
        each agent was the thing the run was waiting on; when steps overlap (event-driven), only the last-finishing one counts.
      </PageHeader>
      <div className="mb-4">
        <Segmented size="sm" value={arch} onChange={setArch} options={[
          { value: "all", label: "All architectures" }, { value: "sequential", label: "Sequential" },
          { value: "hierarchical", label: "Hierarchical" }, { value: "event", label: "Event-driven" },
        ]} />
      </div>
      {error && <ErrorNote error={error} />}
      {!data ? (
        <Skeleton className="h-72" />
      ) : data.length === 0 ? (
        <Empty title="No traces for this selection">Agent metrics appear once runs have been recorded.</Empty>
      ) : (
        <>
          <Panel eyebrow="Latency" title="Median and P95 per call">
            <div className="flex flex-col gap-3">
              {data.map((a) => (
                <div key={a.agent} className="grid grid-cols-[120px_1fr_120px] items-center gap-3 sm:grid-cols-[150px_1fr_150px]">
                  <span className="flex items-center gap-2 text-[12.5px]">
                    <span className="inline-block h-[8px] w-[8px] rounded-[2px]" style={{ background: laneColor(a.agent) }} />
                    {AGENT_LABEL[a.agent] ?? a.agent}
                  </span>
                  <div className="relative h-[14px] rounded-[3px] bg-sunken">
                    <div className="bar-grow absolute inset-y-0 left-0 rounded-[3px]" style={{ width: `${(a.p95_ms / maxP95) * 100}%`, background: laneColor(a.agent, 0.25) }} />
                    <div className="bar-grow absolute inset-y-0 left-0 rounded-[3px]" style={{ width: `${(a.median_ms / maxP95) * 100}%`, background: laneColor(a.agent, 0.9) }} />
                  </div>
                  <span className="num text-right text-[12px]">{fmtMs(a.median_ms)} <span className="text-faint">/ {fmtMs(a.p95_ms)}</span></span>
                </div>
              ))}
            </div>
            <div className="mt-3 text-[11.5px] text-faint">Solid: median · light: P95</div>
          </Panel>

          <div className="mt-6">
            <TableWrap>
              <thead>
                <tr>
                  <Th>Agent</Th><Th>Role</Th><Th right>Calls</Th><Th right>Mean</Th><Th right>Tokens in</Th>
                  <Th right>Tokens out</Th><Th right>Cost</Th><Th right>Cost share</Th><Th right>Critical path</Th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.agent}>
                    <Td className="font-medium">{AGENT_LABEL[a.agent] ?? a.agent}</Td>
                    <Td className="text-[12px] text-muted">{ROLE[a.agent]}</Td>
                    <Td right mono>{a.calls}</Td>
                    <Td right mono>{fmtMs(a.mean_ms)}</Td>
                    <Td right mono>{fmtTokens(a.tokens_in_mean)}</Td>
                    <Td right mono>{fmtTokens(a.tokens_out_mean)}</Td>
                    <Td right mono>{fmtUsd(a.cost_usd)}</Td>
                    <Td right mono>{fmtPct(a.cost_share)}</Td>
                    <Td right mono className={a.critical_path_share === Math.max(...data.map((d) => d.critical_path_share)) ? "font-medium text-accent" : ""}>{fmtPct(a.critical_path_share)}</Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </>
      )}
    </>
  );
}
