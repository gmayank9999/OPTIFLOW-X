"""Builds CrewAI LLM instances per agent role and meters their token usage.

Every LLM call in the system goes through `call()`, which snapshots the
LLM's cumulative usage counters before and after the task and prices the
difference. That's what makes per-agent cost, cost share, and the per-run
USD cap real numbers instead of placeholders.
"""

from __future__ import annotations

import os

from crewai import LLM, Agent, Task

from optiflow.core.config import model_for, price

# CrewAI's global event listener prints a boxed panel for every task and
# LLM call regardless of Agent(verbose=False), which buries our own step
# output. Off unless OPTIFLOW_CREWAI_CONSOLE=1.
if os.getenv("OPTIFLOW_CREWAI_CONSOLE") != "1":
    try:
        from crewai.events.event_listener import event_listener as _crewai_listener

        _crewai_listener.formatter.verbose = False
    except Exception:  # noqa: BLE001 - cosmetic; never block a run over it
        pass
from optiflow.core.schemas import TokenUsage


def llm_for(role: str, temperature: float = 0.2, assignment: str | None = None) -> LLM:
    return LLM(model=model_for(role, assignment), temperature=temperature)


def _usage_snapshot(llm) -> tuple[int, int, int]:
    try:
        u = llm.get_token_usage_summary()
        return int(u.prompt_tokens), int(u.completion_tokens), int(u.successful_requests)
    except Exception:  # noqa: BLE001 - providers without usage tracking report zero
        return 0, 0, 0


def call(agent: Agent, description: str, expected_output: str) -> tuple[str, TokenUsage]:
    """Run one task on `agent` and return (text, usage for this call only)."""
    before = _usage_snapshot(agent.llm)
    task = Task(description=description, expected_output=expected_output, agent=agent)
    output = task.execute_sync(agent)
    after = _usage_snapshot(agent.llm)

    prompt_tokens = after[0] - before[0]
    completion_tokens = after[1] - before[1]
    calls = max(after[2] - before[2], 1)
    model = getattr(agent.llm, "model", "")
    # Some providers report the model without its "provider/" prefix.
    usage = TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        calls=calls,
        cost_usd=price(_full_model_name(agent.llm, model), prompt_tokens, completion_tokens),
    )
    return str(output.raw if hasattr(output, "raw") else output), usage


def _full_model_name(llm, model: str) -> str:
    if "/" in model:
        return model
    provider = getattr(llm, "provider", None)
    return f"{provider}/{model}" if provider else model
