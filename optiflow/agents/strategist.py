"""Optimization Strategist agent.

The only agent that combines all three sources of evidence: the profile,
retrieved technique knowledge (RAG), and the XGBoost ranking prior. It
sees the current best source with line numbers, so "target the hotspot"
is something it can actually do.

Prompting styles (Section 13.1):
- structured: one call, RAG + ranking pre-injected into the prompt.
- react: RAG and ranking are *tools* the agent decides whether to call.
- reflection: draft plan, then a self-critique call that revises it.

Output is parsed and validated against OptimizationPlan; a parse failure
gets one retry with the error fed back, and a second failure raises
PlanError (which the architecture records as a rejected attempt).
Ablation switches (use_rag / use_xgb) blank out the corresponding evidence.
"""

from __future__ import annotations

import json
import re

from crewai import Agent
from crewai.tools import tool

from optiflow.agents.common import PlanError, make_agent as _make_agent, numbered
from optiflow.agents.prompts import strategist as prompts
from optiflow.core import llm
from optiflow.core.schemas import STRATEGY_NAMES, OptimizationPlan, ProfileReport, ProgramSummary, TokenUsage
from optiflow.knowledge.retriever import retrieve, retrieve_text
from optiflow.ml.predictor import rank as rank_strategies
from optiflow.security.guardrails import check_llm_output

ALIASES = {
    "loop_interchange": "interchange", "loop_permutation": "interchange", "permutation": "interchange",
    "loop_tiling": "tiling", "blocking": "tiling", "cache_blocking": "tiling", "loop_blocking": "tiling",
    "vectorization": "vectorize", "simd": "vectorize", "auto_vectorization": "vectorize",
    "loop_unrolling": "unroll", "unrolling": "unroll",
    "loop_fusion": "fusion", "loop_fission": "fission", "loop_distribution": "fission",
    "aos_to_soa": "soa", "struct_of_arrays": "soa", "data_layout": "soa", "aos2soa": "soa",
    "hoisting": "hoist", "licm": "hoist", "loop_invariant_code_motion": "hoist",
    "strength_reduction": "hoist", "code_motion": "hoist",
    "memoization": "memoize", "dynamic_programming": "memoize", "caching": "memoize",
    "compiler_flags": "flags", "flag": "flags", "compiler_flag": "flags",
    "algorithm": "algorithmic", "algorithmic_change": "algorithmic", "algorithm_change": "algorithmic",
    "better_algorithm": "algorithmic",
}


PERSONAS = tuple(prompts.PERSONAS)


def make_agent(assignment: str | None = None, tools: list | None = None, persona: str = "default") -> Agent:
    p = prompts.PERSONAS.get(persona, prompts.PERSONAS["default"])
    return _make_agent(
        "strategist",
        title=p["title"],
        goal=(
            "Choose the source- and flag-level optimizations most likely to give a "
            "verified speedup for this program, without changing its output."
        ),
        backstory=p["backstory"],
        assignment=assignment,
        temperature=0.2,
        tools=tools,
        max_iter=6 if tools else 3,
    )


def build_context(
    summary: ProgramSummary,
    profile: ProfileReport,
    best_source: str,
    best_speedup: float,
    best_flags: list[str],
    compare_mode: str = "exact",
    history_compact: str = "",
    shared_context: str = "",
    use_rag: bool = True,
    use_xgb: bool = True,
    instructions: str = "",
    persona: str = "default",
) -> dict:
    rag_chunks = retrieve(summary, profile, k=4) if use_rag else []
    xgb_ranked = rank_strategies(summary.features, top_k=6) if use_xgb else []
    unsafe = ", -ffast-math (float_tol only)" if compare_mode == "float_tol" else ""
    return {
        "program_id": summary.program_id,
        "lang": summary.language,
        "compare_mode": "with a float tolerance (float_tol)" if compare_mode == "float_tol" else "EXACTLY (byte-identical)",
        "best_speedup": best_speedup,
        "best_flags": " ".join(best_flags),
        "source": numbered(best_source),
        "summary_text": summary.summary_text or "(none)",
        "features_json": json.dumps(summary.features),
        "profile_json": json.dumps({
            "baseline_runtime_ms": round(profile.baseline_runtime_ms, 2),
            "ipc": profile.ipc,
            "l1_miss_rate": profile.l1_miss_rate,
            "llc_miss_rate": profile.llc_miss_rate,
            "branch_miss_rate": profile.branch_miss_rate,
            "hotspots": [h.model_dump() for h in profile.hotspots],
            "bottleneck": profile.bottleneck_text,
        }),
        "xgb_ranked": ", ".join(f"{n} {p:.2f}" for n, p in xgb_ranked) if xgb_ranked else "(disabled)",
        "rag_chunks": "\n---\n".join(rag_chunks) if rag_chunks else "(disabled)",
        "history_compact": history_compact or "(no attempts yet)",
        "shared_context": (f"\nOTHER AGENTS' NOTES:\n{shared_context}\n" if shared_context else "")
        + (prompts.USER_GUIDANCE.format(instructions=instructions) if instructions else "")
        + (f"\n{prompts.PERSONAS[persona]['focus']}\n" if prompts.PERSONAS.get(persona, {}).get("focus") else ""),
        "unsafe_flags": unsafe,
        "_features": summary.features,
        "_persona": persona,
    }


def plan(
    assignment: str | None,
    context: dict,
    attempt: int,
    prompt_style: str = "structured",
) -> tuple[OptimizationPlan, TokenUsage, dict]:
    """Returns (plan, usage, info) where info records prompt sizes and the
    tool calls a ReAct agent made, for tracing."""
    usage = TokenUsage()
    info: dict = {"style": prompt_style, "tool_calls": []}
    fmt = {k: v for k, v in context.items() if not k.startswith("_")}

    persona = context.get("_persona", "default")
    if prompt_style == "react":
        agent = make_agent(assignment, tools=_react_tools(context["_features"], info), persona=persona)
        prompt = prompts.REACT.format(**fmt)
    else:
        agent = make_agent(assignment, persona=persona)
        template = {"reflection": prompts.REFLECTION_DRAFT, "few_shot": prompts.FEW_SHOT}.get(
            prompt_style, prompts.STRUCTURED)
        prompt = template.format(**fmt)

    info["prompt_chars"] = len(prompt)
    result = _ask_for_plan(agent, prompt, attempt, usage)

    if prompt_style == "reflection":
        critique = prompts.REFLECTION_CRITIQUE.format(
            program_id=context["program_id"],
            draft_plan_json=json.dumps(result.model_dump(exclude={"attempt"})),
            profile_json=context["profile_json"],
            history_compact=context["history_compact"],
        )
        info["draft"] = result.model_dump()
        result = _ask_for_plan(agent, critique, attempt, usage)

    return result, usage, info


def plan_guardrail(text: str) -> tuple[bool, str]:
    """CrewAI task guardrail: the answer must parse into a valid plan and
    must not carry injected directives or abuse into the rest of the
    pipeline. On failure CrewAI re-asks the model with this reason."""
    scan = check_llm_output(text, "strategist_plan")
    if not scan.ok:
        return False, f"output rejected by guardrail ({scan.summary()}); answer with the plan JSON only"
    try:
        coerce_plan(text, 0)
    except (ValueError, TypeError) as exc:
        return False, f"invalid plan: {exc}. Answer with ONLY the JSON object."
    return True, "ok"


def _ask_for_plan(agent: Agent, prompt: str, attempt: int, usage: TokenUsage) -> OptimizationPlan:
    try:
        text, u = llm.call(agent, prompt, "OptimizationPlan JSON only, no prose.",
                           guardrail=plan_guardrail, guardrail_retries=1)
    except llm.GuardrailFailed as exc:
        raise PlanError(f"plan rejected by guardrail after retry: {exc}") from exc
    usage.add(u)
    try:
        return coerce_plan(text, attempt)
    except (ValueError, TypeError) as exc:  # guardrail passed but parsing still failed
        raise PlanError(f"unparseable plan: {exc}") from exc


def _react_tools(features: dict, info: dict) -> list:
    @tool("knowledge_search")
    def knowledge_search(query: str) -> str:
        """Search the compiler-optimization knowledge base (technique cards) for a query."""
        info["tool_calls"].append({"tool": "knowledge_search", "query": query})
        return "\n---\n".join(retrieve_text(query, k=3)) or "(no results)"

    @tool("predict_strategies")
    def predict_strategies() -> str:
        """Ranking of strategies by the ML predictor's estimated success probability for this program."""
        info["tool_calls"].append({"tool": "predict_strategies"})
        return json.dumps(rank_strategies(features, top_k=6))

    return [knowledge_search, predict_strategies]


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def normalize_name(name: str) -> str | None:
    key = re.sub(r"[\s\-]+", "_", str(name).strip().lower())
    key = ALIASES.get(key, key)
    return key if key in STRATEGY_NAMES else None


def coerce_plan(text: str, attempt: int) -> OptimizationPlan:
    """Parse model output into an OptimizationPlan, tolerating code fences,
    surrounding prose and strategy-name synonyms. Raises ValueError when
    nothing usable is left."""
    raw = str(text).strip()
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        raise ValueError("no JSON object found in the answer")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("answer must be a JSON object")

    strategies = []
    for s in data.get("strategies") or []:
        if not isinstance(s, dict):
            continue
        name = normalize_name(s.get("name", ""))
        if name is None:
            continue
        try:
            confidence = min(1.0, max(0.0, float(s.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        strategies.append({
            "name": name,
            "target": None if s.get("target") is None else str(s.get("target")),
            "params": s.get("params") if isinstance(s.get("params"), dict) else {},
            "rationale": str(s.get("rationale", ""))[:500],
            "confidence": confidence,
        })
    if not strategies:
        raise ValueError(f"no valid strategies; names must be one of {', '.join(STRATEGY_NAMES)}")

    flags = data.get("flags") or ["-O2"]
    if isinstance(flags, str):
        flags = flags.split()
    compiler = data.get("compiler") if data.get("compiler") in ("gcc", "clang") else "gcc"
    return OptimizationPlan(attempt=attempt, strategies=strategies, compiler=compiler,
                            flags=[str(f) for f in flags])
