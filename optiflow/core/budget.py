"""Attempt and cost budget tracking for a single optimization run.

Stopping rule (deterministic, never the LLM's call):
  - the attempt budget is used up, or
  - the run's LLM spend reached the USD cap, or
  - two consecutive *accepted* attempts each improved the best speedup by
    less than 3% (diminishing returns), or
  - three consecutive attempts were rejected (the Strategist is stuck).

Rejections deliberately don't count toward "diminishing returns": a
failed tiling attempt says nothing about whether a different strategy
could still help, and counting it would end most runs after two misses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_GAIN_PCT = 3.0
MAX_CONSECUTIVE_REJECTS = 3


@dataclass
class RunBudget:
    max_attempts: int
    max_usd: float
    spent_usd: float = 0.0
    attempt: int = 0
    outcomes: list[tuple[bool, float]] = field(default_factory=list)  # (accepted, gain_pct)

    def record_call(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd

    def record_attempt(self, accepted: bool, gain_pct: float = 0.0) -> None:
        self.attempt += 1
        self.outcomes.append((accepted, gain_pct))

    def stop_reason(self) -> str:
        if self.attempt >= self.max_attempts:
            return "attempt_budget"
        if self.max_usd > 0 and self.spent_usd >= self.max_usd:
            return "cost_cap"
        last_two = self.outcomes[-2:]
        if len(last_two) == 2 and all(ok for ok, _ in last_two) and all(g < MIN_GAIN_PCT for _, g in last_two):
            return "diminishing_returns"
        recent = self.outcomes[-MAX_CONSECUTIVE_REJECTS:]
        if len(recent) == MAX_CONSECUTIVE_REJECTS and not any(ok for ok, _ in recent):
            return "consecutive_rejects"
        return ""

    def exhausted(self) -> bool:
        return bool(self.stop_reason())
