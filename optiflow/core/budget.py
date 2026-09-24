"""Attempt and cost budget tracking for a single optimization run."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunBudget:
    max_attempts: int
    max_usd: float
    spent_usd: float = 0.0
    attempt: int = 0
    recent_gains: list[float] = field(default_factory=list)

    def record_call(self, cost_usd: float) -> None:
        self.spent_usd += cost_usd

    def record_attempt(self, gain_pct: float) -> None:
        self.attempt += 1
        self.recent_gains.append(gain_pct)

    def exhausted(self) -> bool:
        if self.attempt >= self.max_attempts:
            return True
        if self.spent_usd >= self.max_usd:
            return True
        if len(self.recent_gains) >= 2 and all(g < 3.0 for g in self.recent_gains[-2:]):
            return True
        return False
