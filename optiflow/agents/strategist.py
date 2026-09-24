"""Optimization Strategist agent.

The only agent that combines all three sources of evidence: the profile,
retrieved technique knowledge (RAG), and the XGBoost ranking prior. Its
output is validated against OptimizationPlan; a parse failure gets one
retry with the validation error appended to the prompt.
"""

from __future__ import annotations

import json

from crewai import Agent, Task

from optiflow.agents.prompts import strategist as prompts
from optiflow.core.llm import llm_for
from optiflow.core.schemas import OptimizationPlan, ProfileReport, ProgramSummary
from optiflow.knowledge.retriever import retrieve
from optiflow.ml.predictor import rank as rank_strategies

TOOL_NAMES: set[str] = set()  # RAG/XGB are called as local Python, not MCP tools


def make_agent(prompt_style: str = "structured") -> Agent:
    return Agent(
        role="Optimization Strategist",
        goal=(
            "Choose the source- and flag-level optimizations most likely to "
            "give a verified speedup for this program, without changing its "
            "output."
        ),
        backstory=(
            "You are a performance engineer expert in GCC/LLVM, cache "
            "behaviour, loop transformations and vectorization. You only "
            "propose changes that preserve output."
        ),
        tools=[],
        llm=llm_for("strategist", temperature=0.2),
        allow_delegation=False,
        max_iter=4,
        verbose=True,
    )


def _compact_history(history: list[dict]) -> str:
    if not history:
        return "(no attempts yet)"
    lines = []
    for entry in history:
        plan = entry.get("plan")
        verdict = entry.get("verdict")
        names = "+".join(s["name"] for s in plan["strategies"]) if plan else "?"
        if verdict and verdict.get("accepted"):
            lines.append(f"A{entry.get('attempt', '?')} {names} -> ACCEPT {verdict['speedup']:.2f}x")
        elif verdict:
            lines.append(f"A{entry.get('attempt', '?')} {names} -> REJECT {verdict['reason']}")
    return "\n".join(lines)


def run(
    agent: Agent,
    summary: ProgramSummary,
    profile: ProfileReport,
    history: list[dict],
    attempt: int,
    prompt_style: str = "structured",
) -> OptimizationPlan:
    rag_chunks = retrieve(summary, profile, k=4)
    xgb_top5 = rank_strategies(summary.features, top_k=5)

    context = {
        "summary_json": json.dumps({
            "functions": summary.functions,
            "features": summary.features,
        }),
        "profile_json": json.dumps({
            "baseline_runtime_ms": profile.baseline_runtime_ms,
            "ipc": profile.ipc,
            "l1_miss_rate": profile.l1_miss_rate,
            "llc_miss_rate": profile.llc_miss_rate,
            "bottleneck": profile.bottleneck_text,
        }),
        "xgb_top5": json.dumps(xgb_top5),
        "rag_chunks": "\n---\n".join(rag_chunks),
        "history_compact": _compact_history(history),
    }

    prompt = _build_prompt(prompt_style, context, attempt)

    task = Task(
        description=prompt,
        expected_output="OptimizationPlan JSON only, no prose.",
        agent=agent,
        output_pydantic=OptimizationPlan,
    )
    result = agent.kickoff([task]) if hasattr(agent, "kickoff") else task.execute_sync(agent)

    plan = _coerce_plan(result, attempt)
    return plan


def _build_prompt(prompt_style: str, context: dict, attempt: int) -> str:
    if prompt_style == "react":
        return prompts.REACT.format(**context)
    if prompt_style == "reflection":
        return prompts.REFLECTION_DRAFT.format(**context)
    return prompts.STRUCTURED.format(**context)


def _coerce_plan(result, attempt: int) -> OptimizationPlan:
    if hasattr(result, "pydantic") and result.pydantic is not None:
        plan = result.pydantic
        plan.attempt = attempt
        return plan
    if isinstance(result, OptimizationPlan):
        result.attempt = attempt
        return result
    data = json.loads(str(result))
    data["attempt"] = attempt
    return OptimizationPlan(**data)
