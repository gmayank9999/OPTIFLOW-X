"""Program Analyzer agent.

Reads a benchmark program through the MCP tools (get_program,
static_analysis) and asks the LLM for a short structural summary. The
loops/functions/features themselves come straight from tree-sitter, not
from the model, so a bad summary can never corrupt the data the rest of
the pipeline reasons over.
"""

from __future__ import annotations

from crewai import Agent, Task

from optiflow.core.llm import llm_for
from optiflow.core.schemas import ProgramSummary

TOOL_NAMES = {"get_program", "static_analysis"}


def make_agent(tools) -> Agent:
    return Agent(
        role="Program Analyzer",
        goal="Extract an accurate structural summary of the target C/C++ program.",
        backstory=(
            "You read unfamiliar C/C++ source quickly and describe its structure "
            "precisely: what the hot loops do, what they touch in memory, and "
            "which function they live in."
        ),
        tools=tools,
        llm=llm_for("analyzer", temperature=0.1),
        allow_delegation=False,
        max_iter=3,
        verbose=True,
    )


def run(agent: Agent, program_id: str) -> ProgramSummary:
    task = Task(
        description=(
            f"Call get_program('{program_id}') then static_analysis(source, lang) "
            "on its source. Reply with a 3-5 line plain-text summary of the "
            "program's structure: what it computes, which loops are hottest by "
            "nesting depth, and any obviously cache-unfriendly access pattern."
        ),
        expected_output="A short structural summary, 3-5 lines, plain text.",
        agent=agent,
    )
    crew_output = task.execute_sync(agent)
    summary_text = str(crew_output)

    from optiflow.tools import analyze as analyze_tool
    from optiflow.tools import registry

    program = registry.load(program_id)
    analysis = analyze_tool.analyze(program["source"], program["meta"]["language"])

    return ProgramSummary(
        program_id=program_id,
        language=program["meta"]["language"],
        source=program["source"],
        functions=analysis["functions"],
        loops=analysis["loops"],
        features=analysis["features"],
        summary_text=summary_text,
    )
