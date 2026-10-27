"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api, Health, ProgramRow, useApi } from "@/lib/api";
import { CATEGORY_LABEL, cx, fmtMs } from "@/lib/format";
import { Button, Segmented } from "./ui";

const ARCH = [
  { value: "sequential", label: "Sequential", hint: "fixed pipeline, Python loop" },
  { value: "hierarchical", label: "Hierarchical", hint: "a manager LLM picks the next step" },
  { value: "event", label: "Event-driven", hint: "agents react to events; profiling runs in parallel" },
] as const;
const MSG = [
  { value: "blackboard", label: "Blackboard", hint: "shared store, agents pull what they need" },
  { value: "p2p", label: "Peer-to-peer", hint: "messages only along the routing table" },
  { value: "broadcast", label: "Broadcast", hint: "everything to every agent's inbox" },
] as const;
const PROMPT = [
  { value: "structured", label: "Structured" },
  { value: "react", label: "ReAct" },
  { value: "reflection", label: "Reflection" },
] as const;
const VARIANT = [
  { value: "full", label: "Full", hint: "LLM agents + RAG + predictor" },
  { value: "flags_only", label: "Flags only", hint: "-O3 -march=native, no LLM" },
  { value: "rule_only", label: "Rules", hint: "predictor + hand-written templates, no LLM" },
  { value: "no_rag", label: "−RAG", hint: "ablation: Strategist without retrieved technique cards" },
  { value: "no_xgb", label: "−Predictor", hint: "ablation: Strategist without the strategy ranking" },
  { value: "llm_only", label: "LLM only", hint: "ablation: neither RAG nor the predictor" },
] as const;

export function StartRun({ defaultProgram, compact = false }: { defaultProgram?: string; compact?: boolean }) {
  const router = useRouter();
  const { data: programs } = useApi<ProgramRow[]>("/programs");
  const { data: health } = useApi<Health>("/health");
  const [program, setProgram] = useState(defaultProgram ?? "matmul_naive");
  const [architecture, setArchitecture] = useState<string>("sequential");
  const [messaging, setMessaging] = useState<string>("blackboard");
  const [promptStyle, setPromptStyle] = useState<string>("structured");
  const [variant, setVariant] = useState<string>("full");
  const [attempts, setAttempts] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsLlm = !["flags_only", "rule_only"].includes(variant);
  const hasKey = health ? Object.values(health.keys).some(Boolean) : true;
  const grouped = useMemo(() => {
    const g: Record<string, ProgramRow[]> = {};
    for (const p of programs ?? []) (g[p.category] ??= []).push(p);
    return g;
  }, [programs]);
  const selected = programs?.find((p) => p.id === program);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ run_id: string }>("/runs", {
        method: "POST",
        body: JSON.stringify({ program_id: program, architecture, messaging, prompt_style: promptStyle, variant, max_attempts: variant === "flags_only" ? 1 : attempts }),
      });
      router.push(`/run/?id=${res.run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const row = (label: string, control: React.ReactNode, hint?: string) => (
    <div className={cx("grid gap-1.5", !compact && "md:grid-cols-[132px_1fr] md:items-center md:gap-4")}>
      <div className="text-[12.5px] text-muted">{label}</div>
      <div>
        {control}
        {hint && <div className="mt-1 text-[11.5px] text-faint">{hint}</div>}
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      {!defaultProgram &&
        row(
          "Program",
          <select
            value={program}
            onChange={(e) => setProgram(e.target.value)}
            className="w-full rounded-[6px] border border-rule bg-surface px-2.5 py-[6px] font-mono text-[12.5px] outline-none focus:border-ink/40"
          >
            {Object.entries(grouped).map(([cat, list]) => (
              <optgroup key={cat} label={CATEGORY_LABEL[cat] ?? cat}>
                {list.map((p) => (
                  <option key={p.id} value={p.id}>{p.id}</option>
                ))}
              </optgroup>
            ))}
          </select>,
          selected ? `${CATEGORY_LABEL[selected.category] ?? selected.category} · baseline ${fmtMs(selected.baseline_ms)} at -O2 · output compared ${selected.compare === "exact" ? "exactly" : "with tolerance"}` : undefined,
        )}
      {row("Variant", <Segmented size="sm" value={variant} onChange={setVariant} options={VARIANT as any} />, VARIANT.find((v) => v.value === variant)?.hint)}
      {needsLlm && row("Architecture", <Segmented size="sm" value={architecture} onChange={setArchitecture} options={ARCH as any} />, ARCH.find((v) => v.value === architecture)?.hint)}
      {needsLlm && row("Messaging", <Segmented size="sm" value={messaging} onChange={setMessaging} options={MSG as any} />, MSG.find((v) => v.value === messaging)?.hint)}
      {needsLlm && row("Prompting", <Segmented size="sm" value={promptStyle} onChange={setPromptStyle} options={PROMPT as any} />)}
      {variant !== "flags_only" &&
        row(
          "Attempts",
          <div className="flex items-center gap-3">
            <input type="range" min={1} max={8} value={attempts} onChange={(e) => setAttempts(Number(e.target.value))} className="w-40 accent-[rgb(var(--accent))]" />
            <span className="num text-[13px]">{attempts}</span>
          </div>,
        )}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button onClick={submit} disabled={busy || (needsLlm && !hasKey)}>{busy ? "Queuing…" : "Start run"}</Button>
        {needsLlm && !hasKey && <span className="text-[12px] text-warn">No LLM API key configured; flags-only and rule-based runs still work.</span>}
        {error && <span className="text-[12px] text-bad">{error}</span>}
      </div>
    </div>
  );
}
