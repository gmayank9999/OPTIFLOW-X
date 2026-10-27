"""Code Transformer agent.

Gets no tools at all: it only rewrites source based on the Strategist's
plan. Output goes through the safety filter before anything downstream
ever tries to compile it; an unsafe or empty rewrite raises
CandidateRejected, which the architecture records as a rejected attempt.
"""

from __future__ import annotations

import json

from crewai import Agent

from optiflow.agents.codeblock import extract_code, unified_diff
from optiflow.agents.common import CandidateRejected, make_agent as _make_agent
from optiflow.agents.prompts import transformer as prompts
from optiflow.agents.safety import check as safety_check
from optiflow.core import llm
from optiflow.core.schemas import Candidate, OptimizationPlan, TokenUsage
from optiflow.security.guardrails import sanitize_source


def make_agent(assignment: str | None = None) -> Agent:
    return _make_agent(
        "transformer",
        title="Code Transformer",
        goal="Apply exactly the requested transformations to the C/C++ source without changing program output.",
        backstory="You are a meticulous C/C++ engineer. You return complete compilable files only.",
        assignment=assignment,
        temperature=0.0,
        max_iter=2,
    )


def run(
    agent: Agent,
    source: str,
    lang: str,
    plan: OptimizationPlan,
    flags: list[str],
    feedback: str = "",
    compare_mode: str = "exact",
    tolerance: float = 0.0,
) -> tuple[Candidate, TokenUsage]:
    prompt = prompts.TRANSFORM.format(
        lang=lang,
        source=source,
        strategies_json=json.dumps([s.model_dump() for s in plan.strategies]),
        compare_rule=(f"numerically within a relative tolerance of {tolerance:g} (printed values are compared token by token)"
                      if compare_mode == "float_tol"
                      else "BYTE-IDENTICAL, including floating-point results"),
    )
    if feedback:
        prompt += prompts.CRITIC_FEEDBACK_ADDENDUM.format(feedback=feedback)

    try:
        text, usage = llm.call(agent, prompt, "A single fenced code block containing the complete rewritten file.",
                               guardrail=rewrite_guardrail, guardrail_retries=1)
    except llm.GuardrailFailed as exc:
        raise CandidateRejected("guardrail", str(exc)[:400]) from exc
    return make_candidate(source, text, plan, flags), usage


def rewrite_guardrail(text: str) -> tuple[bool, str]:
    """CrewAI task guardrail for rewrites: a complete program, nothing that
    reaches outside the sandbox, and no injected directives in comments
    (which the next agent would otherwise read)."""
    code = extract_code(text)
    if "main" not in code or len(code.strip()) < 20:
        return False, "return the COMPLETE program in one fenced code block"
    is_safe, reason = safety_check(code)
    if not is_safe:
        return False, f"forbidden construct ({reason}); rewrite without it"
    guard = sanitize_source(code)
    if not guard.ok:
        return False, f"remove instruction-like text from comments ({guard.summary()})"
    return True, "ok"


def make_candidate(original: str, llm_text: str, plan: OptimizationPlan, flags: list[str]) -> Candidate:
    new_source = extract_code(llm_text)
    if "main" not in new_source or len(new_source.strip()) < 20:
        raise CandidateRejected("empty_output", "transformer did not return a complete program")
    is_safe, reason = safety_check(new_source)
    if not is_safe:
        raise CandidateRejected("unsafe_candidate", reason or "")
    return Candidate(
        attempt=plan.attempt,
        source=new_source,
        flags=flags,
        compiler=plan.compiler,
        diff=unified_diff(original, new_source),
    )
