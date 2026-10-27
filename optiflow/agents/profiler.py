"""Profiler agent.

Runs the baseline through the profile_program MCP tool (perf counters and
loop-level hotspots, or cachegrind/gprof when perf isn't available) and
asks the LLM to name the bottleneck in plain language for the
Strategist's prompt. The numbers themselves are never touched by the model.
"""

from __future__ import annotations

import json

from crewai import Agent

from optiflow.agents.common import make_agent as _make_agent
from optiflow.agents.mcp_tools import ToolClient
from optiflow.core import llm
from optiflow.core.schemas import ProfileReport, ProgramSummary, TokenUsage


def make_agent(assignment: str | None = None) -> Agent:
    return _make_agent(
        "profiler",
        title="Profiler",
        goal="Turn raw hardware counters into a clear statement of where the program's time goes.",
        backstory=(
            "You read perf/cachegrind output and immediately know whether a "
            "program is cache-bound, branch-bound, or just doing too much work."
        ),
        assignment=assignment,
        temperature=0.1,
    )


def measure(tools: ToolClient, program_id: str) -> ProfileReport:
    """The tool-only half: safe to run before (or in parallel with) analysis."""
    return ProfileReport(**tools.call("profile_program", program_id=program_id))


def interpret(agent: Agent | None, report: ProfileReport, summary: ProgramSummary) -> tuple[ProfileReport, TokenUsage]:
    if agent is None:
        return report, TokenUsage()

    hot_lines = []
    lines = summary.source.splitlines()
    for h in report.hotspots[:2]:
        snippet = "\n".join(lines[h.start_line - 1:h.end_line])
        hot_lines.append(f"{h.time_pct:.0f}% in {h.function}() lines {h.start_line}-{h.end_line}:\n{snippet}")

    sentence, usage = llm.call(
        agent,
        description=(
            f"MEASURED PROFILE ({report.counters_source}): "
            f"{json.dumps(report.model_dump(exclude={'hotspots', 'bottleneck_text'}))}\n"
            f"HOTSPOTS:\n" + ("\n\n".join(hot_lines) or "(none)") + "\n\n"
            f"STRUCTURE: {summary.summary_text}\n\n"
            "In one or two sentences, state the dominant bottleneck (cache misses, "
            "branch mispredictions, redundant work, or algorithmic complexity) and why, "
            "citing the actual numbers and line range. Plain text only."
        ),
        expected_output="One or two sentences naming the bottleneck with supporting numbers.",
    )
    measured = report.bottleneck_text
    report = report.model_copy(update={"bottleneck_text": f"{sentence.strip()} [measured: {measured}]"})
    return report, usage


def run(agent: Agent | None, tools: ToolClient, summary: ProgramSummary) -> tuple[ProfileReport, TokenUsage]:
    return interpret(agent, measure(tools, summary.program_id), summary)
