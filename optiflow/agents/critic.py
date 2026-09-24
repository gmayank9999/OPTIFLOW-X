"""Critic & Verifier.

The accept/reject decision is deterministic and never left to the LLM: a
plan either produced a candidate that compiles, passes every test, and
clears the speedup bar with statistical significance, or it didn't. The
LLM's only job is to explain the rejection and suggest what to try next;
even the stop decision is rule-based.
"""

from __future__ import annotations

from optiflow.core.budget import RunBudget
from optiflow.core.schemas import BenchResult, BuildResult, CompareResult, TestResult, Verdict

MIN_SPEEDUP = 1.05
P_VALUE_THRESHOLD = 0.05


def decide(
    build: BuildResult,
    tests: TestResult | None,
    compare: CompareResult | None,
    budget: RunBudget,
    current_best_speedup: float = 1.0,
) -> Verdict:
    if not build.ok:
        return _reject("compile_error", build.stderr[-500:], budget)

    if tests is None or not tests.all_pass:
        failed = ", ".join(tests.failed_cases) if tests else "unknown"
        return _reject("wrong_output", f"failed cases: {failed}", budget)

    if compare is None:
        return _reject("no_measurement", "benchmark did not produce a result", budget)

    if compare.speedup < MIN_SPEEDUP or compare.p_value >= P_VALUE_THRESHOLD:
        reason = (
            f"speedup {compare.speedup:.3f}x below {MIN_SPEEDUP}x threshold"
            if compare.speedup < MIN_SPEEDUP
            else f"p-value {compare.p_value:.3f} not significant (need < {P_VALUE_THRESHOLD})"
        )
        return _reject("no_significant_gain", reason, budget)

    # Gain relative to the best candidate found so far, not the raw
    # speedup: this is what the "diminishing returns" stop rule tracks.
    improvement_pct = (compare.speedup - current_best_speedup) / current_best_speedup * 100
    budget.record_attempt(improvement_pct)
    return Verdict(
        accepted=True,
        speedup=compare.speedup,
        reason="accepted",
        feedback_for_strategist="",
        stop=budget.exhausted(),
    )


def _reject(reason: str, detail: str, budget: RunBudget) -> Verdict:
    budget.record_attempt(0.0)
    return Verdict(
        accepted=False,
        speedup=1.0,
        reason=reason,
        feedback_for_strategist=f"{reason}: {detail}",
        stop=budget.exhausted(),
    )
