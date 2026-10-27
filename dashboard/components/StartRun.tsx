"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError, GuardrailCheck, Health, ProgramRow, setToken, useApi } from "@/lib/api";
import { CATEGORY_LABEL, cx, fmtMs } from "@/lib/format";
import { Button, Pill, Segmented } from "./ui";

const ARCH = [
  { value: "sequential", label: "Sequential", hint: "fixed pipeline, Python loop" },
  { value: "hierarchical", label: "Hierarchical", hint: "a manager LLM picks the next step" },
  { value: "event", label: "Event-driven", hint: "agents react to events; profiling runs in parallel" },
];
const MSG = [
  { value: "blackboard", label: "Blackboard", hint: "shared store, agents pull what they need" },
  { value: "p2p", label: "Peer-to-peer", hint: "messages only along the routing table" },
  { value: "broadcast", label: "Broadcast", hint: "everything to every agent's inbox" },
];
const PROMPT = [
  { value: "structured", label: "Structured", hint: "one call; RAG + predictor injected" },
  { value: "react", label: "ReAct", hint: "RAG + predictor as tools the agent decides to call" },
  { value: "reflection", label: "Reflection", hint: "draft, self-critique, revise" },
  { value: "few_shot", label: "Few-shot", hint: "three worked profile→plan examples" },
];
const PERSONA = [
  { value: "default", label: "Default", hint: "performance engineer" },
  { value: "compiler_engineer", label: "Compiler eng.", hint: "let the compiler do the work: aliasing, vectorization, flags" },
  { value: "hpc_researcher", label: "HPC researcher", hint: "memory hierarchy, locality, asymptotic wins" },
  { value: "cautious_reviewer", label: "Cautious", hint: "smallest provably output-preserving change" },
];
const CRITIC = [
  { value: "crewai", label: "CrewAI", hint: "rejection feedback from the in-process CrewAI critic" },
  { value: "adk_a2a", label: "ADK via A2A", hint: "a Google ADK agent, reached over the A2A protocol" },
];
const VARIANT = [
  { value: "full", label: "Full", hint: "LLM agents + RAG + predictor" },
  { value: "flags_only", label: "Flags only", hint: "-O3 -march=native, no LLM" },
  { value: "rule_only", label: "Rules", hint: "predictor + hand-written templates, no LLM" },
  { value: "no_rag", label: "−RAG", hint: "ablation: Strategist without retrieved technique cards" },
  { value: "no_xgb", label: "−Predictor", hint: "ablation: Strategist without the strategy ranking" },
  { value: "llm_only", label: "LLM only", hint: "ablation: neither RAG nor the predictor" },
];

const hintOf = (list: { value: string; hint: string }[], v: string) => list.find((x) => x.value === v)?.hint;

export function StartRun({ defaultProgram, compact = false }: { defaultProgram?: string; compact?: boolean }) {
  const router = useRouter();
  const { data: programs } = useApi<ProgramRow[]>("/programs");
  const { data: health } = useApi<Health>("/health");
  const [program, setProgram] = useState(defaultProgram ?? "matmul_naive");
  const [variant, setVariant] = useState("full");
  const [architecture, setArchitecture] = useState("sequential");
  const [messaging, setMessaging] = useState("blackboard");
  const [promptStyle, setPromptStyle] = useState("structured");
  const [persona, setPersona] = useState("default");
  const [critic, setCritic] = useState("crewai");
  const [instructions, setInstructions] = useState("");
  const [screen, setScreen] = useState<GuardrailCheck | null>(null);
  const [attempts, setAttempts] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needToken, setNeedToken] = useState(false);
  const [tokenDraft, setTokenDraft] = useState("");
  const [advanced, setAdvanced] = useState(false);

  const needsLlm = !["flags_only", "rule_only"].includes(variant);
  const hasKey = health ? Object.values(health.keys).some(Boolean) : true;
  const grouped = useMemo(() => {
    const g: Record<string, ProgramRow[]> = {};
    for (const p of programs ?? []) (g[p.category] ??= []).push(p);
    return g;
  }, [programs]);
  const selected = programs?.find((p) => p.id === program);

  // Live guardrail screening of the guidance text (debounced, server-side rules).
  useEffect(() => {
    if (!instructions.trim()) {
      setScreen(null);
      return;
    }
    const id = setTimeout(async () => {
      try {
        setScreen(await api<GuardrailCheck>("/guardrails/check", { method: "POST", body: JSON.stringify({ text: instructions }) }));
      } catch {}
    }, 350);
    return () => clearTimeout(id);
  }, [instructions]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ run_id: string }>("/runs", {
        method: "POST",
        body: JSON.stringify({
          program_id: program, architecture, messaging, prompt_style: promptStyle, variant, persona,
          critic_backend: critic, instructions: needsLlm ? instructions : "",
          max_attempts: variant === "flags_only" ? 1 : attempts,
        }),
      });
      router.push(`/run/?id=${res.run_id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setNeedToken(true);
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const row = (label: string, control: React.ReactNode, hint?: string) => (
    <div className={cx("grid grid-cols-1 gap-1.5", !compact && "md:grid-cols-[120px_1fr] md:items-center md:gap-4")}>
      <div className="text-[12.5px] text-muted">{label}</div>
      <div className="min-w-0">
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
                {list.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
              </optgroup>
            ))}
          </select>,
          selected ? `${CATEGORY_LABEL[selected.category] ?? selected.category} · baseline ${fmtMs(selected.baseline_ms)} at -O2 · output compared ${selected.compare === "exact" ? "exactly" : "with tolerance"}` : undefined,
        )}
      {row("Variant", <Segmented size="sm" value={variant} onChange={setVariant} options={VARIANT} />, hintOf(VARIANT, variant))}
      {needsLlm && (
        <>
          {row("Architecture", <Segmented size="sm" value={architecture} onChange={setArchitecture} options={ARCH} />, hintOf(ARCH, architecture))}
          {row("Prompting", <Segmented size="sm" value={promptStyle} onChange={setPromptStyle} options={PROMPT} />, hintOf(PROMPT, promptStyle))}
          {row("Critic", <Segmented size="sm" value={critic} onChange={setCritic} options={CRITIC} />, hintOf(CRITIC, critic))}
          {!advanced ? (
            <button onClick={() => setAdvanced(true)} className="self-start text-[12px] text-muted hover:text-ink">
              + messaging, persona, guidance
            </button>
          ) : (
            <>
              {row("Messaging", <Segmented size="sm" value={messaging} onChange={setMessaging} options={MSG} />, hintOf(MSG, messaging))}
              {row("Persona", <Segmented size="sm" value={persona} onChange={setPersona} options={PERSONA} />, hintOf(PERSONA, persona))}
              {row(
                "Guidance",
                <div>
                  <textarea
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                    maxLength={600}
                    rows={2}
                    placeholder="Optional hint for the Strategist, e.g. “the matrix is row-major; try interchange first”"
                    className={cx(
                      "w-full resize-y rounded-[6px] border bg-surface px-2.5 py-[6px] text-[12.5px] outline-none focus:border-ink/40",
                      screen && !screen.ok ? "border-bad/60" : "border-rule",
                    )}
                  />
                  {screen && (
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px]">
                      {screen.ok ? (
                        <Pill tone="accent">guardrail: clean</Pill>
                      ) : (
                        <>
                          <Pill tone="bad">guardrail: will be rejected</Pill>
                          {screen.findings.map((f, i) => <Pill key={i} tone="outline">{f.kind}: {f.rule}</Pill>)}
                        </>
                      )}
                    </div>
                  )}
                </div>,
                "Screened for prompt injection and abusive language before anything runs.",
              )}
            </>
          )}
        </>
      )}
      {variant !== "flags_only" &&
        row(
          "Attempts",
          <div className="flex items-center gap-3">
            <input type="range" min={1} max={8} value={attempts} onChange={(e) => setAttempts(Number(e.target.value))} className="w-40 accent-[rgb(var(--accent))]" />
            <span className="num text-[13px]">{attempts}</span>
          </div>,
        )}
      {needToken && (
        <div className="flex flex-wrap items-center gap-2 rounded-[6px] border border-warn/40 bg-warn-soft px-3 py-2 text-[12.5px]">
          <span>This server requires an API token to start runs.</span>
          <input
            type="password"
            value={tokenDraft}
            onChange={(e) => setTokenDraft(e.target.value)}
            placeholder="API token"
            className="w-44 rounded-[5px] border border-rule bg-surface px-2 py-[3px] font-mono text-[12px]"
          />
          <Button variant="ghost" onClick={() => { setToken(tokenDraft); setNeedToken(false); setError(null); }}>Save</Button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <Button onClick={submit} disabled={busy || (needsLlm && !hasKey) || (!!screen && !screen.ok)}>{busy ? "Queuing…" : "Start run"}</Button>
        {needsLlm && !hasKey && <span className="text-[12px] text-warn">No LLM API key configured; flags-only and rule-based runs still work.</span>}
        {error && !needToken && <span className="text-[12px] text-bad">{error}</span>}
      </div>
    </div>
  );
}
