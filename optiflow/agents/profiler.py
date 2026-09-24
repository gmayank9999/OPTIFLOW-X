"""Profiler agent.

Runs the baseline through profile_program (perf counters, or cachegrind
when perf isn't available) and asks the LLM to name the bottleneck in
plain language for the Strategist's prompt. The numbers themselves are
never touched by the model.
"""

from __future__ import annotations

from crewai import Agent, Task

from optiflow.core.llm import llm_for
from optiflow.core.schemas import ProfileReport, ProgramSummary

TOOL_NAMES = {"profile_program"}


def make_agent(tools) -> Agent:
    return Agent(
        role="Profiler",
        goal="Turn raw hardware counters into a clear statement of where the program's time goes.",
        backstory=(
            "You read perf/cachegrind output and immediately know whether a "
            "program is cache-bound, branch-bound, or just doing too much work."
        ),
        tools=tools,
        llm=llm_for("profiler", temperature=0.1),
        allow_delegation=False,
        max_iter=3,
        verbose=True,
    )


def run(agent: Agent, summary: ProgramSummary) -> ProfileReport:
    task = Task(
        description=(
            f"Call profile_program('{summary.program_id}'). Given the counters "
            "it returns, state in one sentence what the dominant bottleneck is "
            "(cache misses, branch mispredictions, or raw instruction count) "
            "and why, referencing the actual numbers."
        ),
        expected_output="One sentence naming the bottleneck with supporting numbers.",
        agent=agent,
    )
    crew_output = agent.kickoff([task]) if hasattr(agent, "kickoff") else task.execute_sync(agent)
    bottleneck_sentence = str(crew_output)

    from optiflow.tools import profile as profile_tool

    report = profile_tool.profile(summary.program_id)
    report.bottleneck_text = bottleneck_sentence or report.bottleneck_text
    return report
