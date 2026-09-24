"""Code Transformer agent.

Gets no tools at all: it only rewrites source based on the Strategist's
plan. Output goes through the safety filter before anything downstream
ever tries to compile it.
"""

from __future__ import annotations

import json

from crewai import Agent, Task

from optiflow.agents.codeblock import extract_code, unified_diff
from optiflow.agents.prompts import transformer as prompts
from optiflow.agents.safety import check as safety_check
from optiflow.core.llm import llm_for
from optiflow.core.schemas import Candidate, OptimizationPlan


def make_agent() -> Agent:
    return Agent(
        role="Code Transformer",
        goal="Apply exactly the requested transformations to the C/C++ source without changing program output.",
        backstory="You are a meticulous C/C++ engineer. You return complete compilable files only.",
        tools=[],
        llm=llm_for("transformer", temperature=0.0),
        allow_delegation=False,
        max_iter=2,
        verbose=True,
    )


def run(
    agent: Agent,
    source: str,
    lang: str,
    plan: OptimizationPlan,
    feedback: str = "",
) -> Candidate:
    prompt = prompts.TRANSFORM.format(
        lang=lang,
        source=source,
        strategies_json=json.dumps([s.model_dump() for s in plan.strategies]),
    )
    if feedback:
        prompt += prompts.CRITIC_FEEDBACK_ADDENDUM.format(feedback=feedback)

    task = Task(
        description=prompt,
        expected_output="A single fenced code block containing the complete rewritten file.",
        agent=agent,
    )
    result = agent.kickoff([task]) if hasattr(agent, "kickoff") else task.execute_sync(agent)

    new_source = extract_code(str(result))
    is_safe, reason = safety_check(new_source)
    if not is_safe:
        raise ValueError(f"transformer output failed the safety filter: {reason}")

    return Candidate(
        attempt=plan.attempt,
        source=new_source,
        flags=plan.flags,
        diff=unified_diff(source, new_source),
    )
