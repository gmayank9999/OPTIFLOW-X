"""Small helpers shared by the agent modules."""

from __future__ import annotations

from crewai import Agent

from optiflow.core.llm import llm_for


class CandidateRejected(Exception):
    """A step produced something that must not reach the compiler
    (unsafe source, empty output). Becomes a rejected attempt, not a crash."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


class PlanError(Exception):
    """The Strategist's output couldn't be turned into a valid plan, even
    after one retry with the validation error fed back."""


def make_agent(role: str, title: str, goal: str, backstory: str, assignment: str | None,
               temperature: float = 0.2, tools: list | None = None, max_iter: int = 3) -> Agent:
    return Agent(
        role=title,
        goal=goal,
        backstory=backstory,
        tools=tools or [],
        llm=llm_for(role, temperature=temperature, assignment=assignment),
        allow_delegation=False,
        max_iter=max_iter,
        verbose=False,
    )


def numbered(source: str) -> str:
    """Source with line numbers, so hotspot line ranges are meaningful to the model."""
    return "\n".join(f"{i:4d} | {line}" for i, line in enumerate(source.splitlines(), start=1))
