"""Critic & Verifier.

The accept/reject decision is deterministic and never left to the LLM: a
plan either produced a candidate that compiles, passes every test and the
sanitizer check, clears the speedup bar with statistical significance,
and beats the current best -- or it didn't. The stop decision is
rule-based too (core/budget.py).

The LLM's only job is `explain()`: turning the evidence of a rejection
into concrete feedback for the Strategist ("in2 has n=33; your tiling
skips the remainder tile"). It runs only on rejections.
"""

from __future__ import annotations

from crewai import Agent

from optiflow.agents.common import make_agent as _make_agent
from optiflow.core import llm
from optiflow.core.budget import RunBudget
from optiflow.core.schemas import BuildResult, CompareResult, TestResult, TokenUsage, Verdict

MIN_SPEEDUP = 1.05
P_VALUE_THRESHOLD = 0.05
# A new best must beat the old one by more than run-to-run noise; without
# this margin, re-measuring the *same* code could "improve" by luck.
MIN_IMPROVEMENT = 1.02


def make_agent(assignment: str | None = None) -> Agent:
    return _make_agent(
        "critic",
        title="Critic and Verifier",
        goal="Explain precisely why a candidate was rejected and what the Strategist should try next.",
        backstory=(
            "You review failed optimization attempts like a senior performance "
            "engineer: you read compiler errors, failing test cases and timing "
            "evidence, and give one concrete, actionable fix."
        ),
        assignment=assignment,
        temperature=0.2,
    )


def decide(
    build: BuildResult,
    tests: TestResult | None,
    compare: CompareResult | None,
    budget: RunBudget,
    current_best_speedup: float = 1.0,
    rejected_reason: str | None = None,
    rejected_detail: str = "",
) -> Verdict:
    if rejected_reason:
        return _reject(rejected_reason, rejected_detail, budget)

    if not build.ok:
        return _reject("compile_error", build.stderr[-500:], budget)

    if tests is None or not tests.all_pass:
        if tests is not None and tests.failed_cases == ["sanitizer"]:
            return _reject("sanitizer_error", tests.sanitizer_report[-800:], budget)
        failed = _describe_failures(tests)
        return _reject("wrong_output", failed, budget)

    if compare is None:
        return _reject("no_measurement", "benchmark did not produce a result", budget)

    if compare.speedup < MIN_SPEEDUP or compare.p_value >= P_VALUE_THRESHOLD:
        reason = (
            f"speedup {compare.speedup:.3f}x below {MIN_SPEEDUP}x threshold"
            if compare.speedup < MIN_SPEEDUP
            else f"p-value {compare.p_value:.3f} not significant (need < {P_VALUE_THRESHOLD})"
        )
        return _reject("no_significant_gain", reason, budget)

    if compare.speedup <= current_best_speedup * MIN_IMPROVEMENT:
        return _reject(
            "no_improvement",
            f"{compare.speedup:.2f}x does not beat the current best {current_best_speedup:.2f}x "
            f"by more than {(MIN_IMPROVEMENT - 1) * 100:.0f}%",
            budget,
        )

    # Gain relative to the best candidate so far: this is what the
    # "diminishing returns" stop rule tracks.
    improvement_pct = (compare.speedup - current_best_speedup) / current_best_speedup * 100
    budget.record_attempt(True, improvement_pct)
    stop_reason = budget.stop_reason()
    return Verdict(
        accepted=True,
        speedup=compare.speedup,
        reason="accepted",
        feedback_for_strategist=(
            f"accepted at {compare.speedup:.2f}x (+{improvement_pct:.1f}% over the previous best); "
            "the next attempt builds on this version"
        ),
        stop=bool(stop_reason),
        stop_reason=stop_reason,
    )


def _describe_failures(tests: TestResult | None) -> str:
    if tests is None:
        return "tests did not run"
    parts = []
    for case in tests.failed_cases:
        d = tests.details.get(case, {})
        status = d.get("status", "failed")
        if status == "wrong_output":
            parts.append(f"{case}: wrong output (got {d.get('actual_head', '')[:60]!r}, "
                         f"expected {d.get('expected_head', '')[:60]!r})")
        else:
            parts.append(f"{case}: {status}")
    return "; ".join(parts) or "unknown failure"


def _reject(reason: str, detail: str, budget: RunBudget) -> Verdict:
    budget.record_attempt(False)
    stop_reason = budget.stop_reason()
    return Verdict(
        accepted=False,
        speedup=1.0,
        reason=reason,
        feedback_for_strategist=f"{reason}: {detail}",
        stop=bool(stop_reason),
        stop_reason=stop_reason,
    )


def explain(agent: Agent | None, verdict: Verdict, plan_summary: str, diff: str) -> tuple[Verdict, TokenUsage]:
    """LLM-written feedback for a rejection. The verdict itself is unchanged."""
    if agent is None or verdict.accepted:
        return verdict, TokenUsage()
    text, usage = llm.call(
        agent,
        description=(
            f"An optimization attempt was rejected.\nPLAN: {plan_summary}\n"
            f"EVIDENCE: {verdict.feedback_for_strategist[:1500]}\n"
            f"DIFF (truncated):\n{diff[:3000]}\n\n"
            "In at most two sentences: the most likely cause, and the single most "
            "promising next step for the Strategist. Plain text."
        ),
        expected_output="Two sentences of concrete feedback.",
    )
    feedback = f"{verdict.feedback_for_strategist[:600]} | critic: {text.strip()}"
    return verdict.model_copy(update={"feedback_for_strategist": feedback}), usage
