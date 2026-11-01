"""Hierarchical architecture: a Manager agent decides what happens next.

After analysis and profiling, the Manager LLM looks at the run so far and
chooses one action per turn:

  - "plan":        ask the Strategist for a new plan (full attempt)
  - "retransform": keep the last plan, have the Transformer redo it with
                   the Critic's feedback (cheaper; skips the Strategist)
  - "stop":        end the run

Guardrails keep the comparison fair and the run bounded: the attempt
budget, cost cap and stop rules are still enforced deterministically; the
Manager can't stop before the first attempt; "retransform" is only valid
when the last attempt failed for a fixable correctness reason; and an
unparseable or invalid decision falls back to "plan" (counted in
`manager_fallbacks`). This is the "custom manager in plain Python"
fallback from the plan's risk register -- CrewAI's built-in hierarchical
process can loop unboundedly, which is exactly what an experiment can't
afford.
"""

from __future__ import annotations

import json
import re

from optiflow.agents.common import make_agent
from optiflow.agents.mcp_tools import McpToolClient
from optiflow.architectures.base import Architecture
from optiflow.architectures.pipeline import Pipeline
from optiflow.core import llm
from optiflow.core.schemas import OptimizationPlan, RunState

ACTIONS = ("plan", "retransform", "stop")
RETRANSFORMABLE = {"compile_error", "wrong_output", "sanitizer_error", "empty_output"}

MANAGER_PROMPT = """\
You manage a team optimizing the C program `{program_id}`.
Profile: {bottleneck}
Current best: {best:.2f}x over -O2. Attempts used: {used}/{budget}. Spend: ${spent:.4f} of ${cap:.2f}.
History:
{history}

Choose the next action:
- "plan": the Strategist proposes a new optimization (use after a success, or when the last idea is exhausted).
- "retransform": re-apply the LAST plan with the Critic's feedback (only sensible when the last attempt
  failed on compile_error / wrong_output / sanitizer_error and the idea itself still looks right).
- "stop": end the run (when further gains look unlikely to justify the cost).
Return ONLY JSON: {{"action": "plan" | "retransform" | "stop", "reason": "<one sentence>"}}"""


class Hierarchical(Architecture):
    name = "hierarchical"

    def run(self, program_id: str) -> RunState:
        tools_cm = self._tools or McpToolClient()
        with tools_cm as tools:
            p = Pipeline(self.cfg, self.channel, tools, program_id, self.name, emit=self.emit)
            p.extra_stats["manager_fallbacks"] = 0
            try:
                with p.tracer.start_as_current_span("run", attributes={"program": program_id, "architecture": self.name}):
                    p.start()
                    p.analyze()
                    p.profile()
                    stop_reason = self._loop(p)
                return p.finish(stop_reason)
            except Exception as exc:  # noqa: BLE001
                p.fail(exc)
                raise

    def _loop(self, p: Pipeline) -> str:
        manager = make_agent(
            "manager", title="Optimization Manager",
            goal="Direct the optimization team to the best verified speedup within budget.",
            backstory="You run a small performance-engineering team and decide what they work on next.",
            assignment=self.cfg.model_assignment, temperature=0.1,
        ) if self.cfg.uses_llm else None

        last_plan: OptimizationPlan | None = None
        last_verdict = None
        for attempt in range(1, self.cfg.max_attempts + 1):
            action = "plan" if attempt == 1 else self._decide(p, manager, attempt, last_verdict)
            if action == "stop":
                return "manager_stop"

            if action == "retransform" and last_plan is not None:
                verdict = p.attempt(attempt, plan=last_plan, feedback=last_verdict.feedback_for_strategist)
            else:
                verdict = p.attempt(attempt)
            if verdict is None:
                return "no_more_strategies"

            plans = [h for h in p.state.history if h["attempt"] == attempt and h.get("plan")]
            last_plan = OptimizationPlan(**plans[-1]["plan"]) if plans else last_plan
            last_verdict = verdict
            if verdict.stop:
                return verdict.stop_reason
        return "attempt_budget"

    def _decide(self, p: Pipeline, manager, attempt: int, last_verdict) -> str:
        allowed = {"plan", "stop"}
        if last_verdict is not None and not last_verdict.accepted and last_verdict.reason in RETRANSFORMABLE:
            allowed.add("retransform")

        if manager is None:  # LLM-free variants: deterministic policy
            return "retransform" if "retransform" in allowed else "plan"

        with p.step("manager", attempt=attempt) as rec:
            prompt = MANAGER_PROMPT.format(
                program_id=p.state.program_id,
                bottleneck=(p.state.profile.bottleneck_text if p.state.profile else "")[:500],
                best=p.state.best["speedup"], used=attempt - 1, budget=self.cfg.max_attempts,
                spent=p.budget.spent_usd, cap=self.cfg.max_usd_per_run,
                history=p._strategist_history() or "(none)",
            )
            try:
                text, rec["usage"] = llm.call(manager, prompt, 'JSON {"action": ..., "reason": ...}')
                action, reason = _parse_decision(text)
            except llm.LLMCallError as exc:
                action, reason = "invalid", f"manager call failed ({str(exc)[:80]})"
            if action not in allowed:
                p.extra_stats["manager_fallbacks"] += 1
                reason = f"invalid action {action!r} -> plan ({reason})"
                action = "plan"
            rec["summary"] = f"{action}: {reason}"
            rec["data"] = {"action": action, "reason": reason, "allowed": sorted(allowed)}
        return action


def _parse_decision(text: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", str(text), re.DOTALL)
    if not match:
        return "invalid", "no JSON"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "invalid", "bad JSON"
    action = str(data.get("action", "")).strip().lower()
    return (action if action in ACTIONS else f"invalid:{action}"), str(data.get("reason", ""))[:300]
