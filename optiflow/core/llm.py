"""Builds CrewAI LLM instances per agent role and meters their token usage.

Every LLM call in the system goes through `call()`, which snapshots the
LLM's cumulative usage counters before and after the task and prices the
difference. That's what makes per-agent cost, cost share, and the per-run
USD cap real numbers instead of placeholders.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import re
import time
from typing import Callable

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


TRANSIENT_MARKERS = ("getaddrinfo", "connecterror", "connection reset", "timed out", "timeout",
                     "temporarily unavailable", "503", "502", "429", "resource_exhausted", "unavailable")
MAX_TRIES = 4


class QuotaExhausted(RuntimeError):
    """The provider's quota is used up for a long time (e.g. a per-day free
    tier limit). Retrying within a run is pointless; callers running many
    runs (the experiment matrix) should stop instead of failing every cell."""


_RETRY_DELAY = re.compile(r"retryDelay'?\"?:\s*'?\"?(\d+)s", re.I)
LONG_QUOTA_SECONDS = 120


def _quota_exhausted(exc: Exception) -> bool:
    text = str(exc)
    if "429" not in text and "RESOURCE_EXHAUSTED" not in text:
        return False
    if re.search(r"PerDay|per day|daily", text, re.I):
        return True
    m = _RETRY_DELAY.search(text)
    return bool(m and int(m.group(1)) > LONG_QUOTA_SECONDS)


def _is_transient(exc: Exception) -> bool:
    if _quota_exhausted(exc):
        return False
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in TRANSIENT_MARKERS)


# CrewAI raises a plain Exception("Task failed <name> validation after N retries...").
_GUARDRAIL_EXHAUSTED = re.compile(r"Task failed .{0,80}validation after \d+ retr", re.I)


class GuardrailFailed(RuntimeError):
    """A CrewAI task guardrail kept rejecting the model's output after retries."""


# --- monitoring -------------------------------------------------------------
# The pipeline installs a sink for the duration of each agent step; every
# CrewAI step callback (thought / tool call / final answer), task callback
# and guardrail decision is forwarded to it. Context-local, so concurrent
# steps in the event-driven architecture don't mix their streams.
_monitor: contextvars.ContextVar[Callable[[dict], None] | None] = contextvars.ContextVar("optiflow_monitor", default=None)


@contextlib.contextmanager
def monitor(sink: Callable[[dict], None]):
    token = _monitor.set(sink)
    try:
        yield
    finally:
        _monitor.reset(token)


MONITOR_FAILURES = {"count": 0}


def _emit(kind: str, **data) -> None:
    sink = _monitor.get()
    if sink is not None:
        try:
            sink({"kind": kind, **data})
        except Exception as exc:  # noqa: BLE001 - monitoring must never break a call...
            # ...but it must not fail silently either: count it and say so once.
            MONITOR_FAILURES["count"] += 1
            if MONITOR_FAILURES["count"] == 1:
                import warnings

                warnings.warn(f"OPTIFLOW monitor sink failed ({type(exc).__name__}: {exc}); "
                              "events are being dropped", RuntimeWarning, stacklevel=2)


def _step_callback(step) -> None:
    """CrewAI Agent.step_callback: AgentAction (thought + tool call),
    ToolResult, or AgentFinish."""
    name = type(step).__name__
    data = {"step_type": name}
    for attr in ("thought", "tool", "tool_input", "result", "output", "text"):
        value = getattr(step, attr, None)
        if value:
            data[attr] = str(value)[:600]
    _emit("crewai_step", **data)


def _task_callback(output) -> None:
    """CrewAI Task.callback: fires once the task (including guardrail
    retries) has produced its final output."""
    raw = str(getattr(output, "raw", output))
    _emit("crewai_task_done", agent_role=str(getattr(output, "agent", "")), chars=len(raw), preview=raw[:300])


def _wrap_guardrail(guardrail: Callable[[str], tuple[bool, str]]):
    """Adapts a text-level check to CrewAI's Task guardrail signature and
    reports every decision to the monitor."""
    # No return annotation on purpose: CrewAI validates guardrail callables'
    # annotations as typing.Tuple[bool, Any], which a postponed (string)
    # annotation under `from __future__ import annotations` fails.
    def check(task_output):
        raw = str(getattr(task_output, "raw", task_output))
        ok, detail = guardrail(raw)
        _emit("guardrail", stage="task_output", ok=ok, detail=str(detail)[:300])
        return (True, task_output) if ok else (False, str(detail))
    return check


def call(agent: Agent, description: str, expected_output: str,
         guardrail: Callable[[str], tuple[bool, str]] | None = None,
         guardrail_retries: int = 1) -> tuple[str, TokenUsage]:
    """Run one task on `agent` and return (text, usage for this call only).

    - `guardrail(text) -> (ok, reason)` becomes a CrewAI task guardrail:
      on failure CrewAI re-asks the model with the reason, up to
      `guardrail_retries` times, then GuardrailFailed is raised.
    - CrewAI's step and task callbacks feed the active monitor.
    - Transient failures (DNS blips, dropped connections, rate limits,
      5xx) are retried with exponential backoff; anything else propagates.
    """
    agent.step_callback = _step_callback
    before = _usage_snapshot(agent.llm)
    for attempt in range(1, MAX_TRIES + 1):
        try:
            task = Task(
                description=description, expected_output=expected_output, agent=agent,
                callback=_task_callback,
                guardrail=_wrap_guardrail(guardrail) if guardrail else None,
                guardrail_max_retries=guardrail_retries,
            )
            output = task.execute_sync(agent)
            break
        except Exception as exc:  # noqa: BLE001 - classified below
            if guardrail and _GUARDRAIL_EXHAUSTED.search(str(exc)):
                _emit("guardrail", stage="exhausted", ok=False, detail=str(exc)[:300])
                raise GuardrailFailed(str(exc)) from exc
            if _quota_exhausted(exc):
                _emit("llm_error", error="provider quota exhausted")
                raise QuotaExhausted(str(exc)[:600]) from exc
            if attempt == MAX_TRIES or not _is_transient(exc):
                _emit("llm_error", error=f"{type(exc).__name__}: {str(exc)[:300]}")
                raise
            _emit("llm_retry", attempt=attempt, error=f"{type(exc).__name__}: {str(exc)[:200]}")
            time.sleep(2 ** attempt)  # 2, 4, 8 s
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
