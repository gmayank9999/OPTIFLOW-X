"""Compiler & Executor agent.

Compiles the candidate and runs the correctness tests. On a compile
failure, gives the LLM the source and the last 2000 characters of stderr
and asks for a fix, up to two tries, before giving up and letting the
Critic reject with the compile error as evidence.
"""

from __future__ import annotations

from crewai import Agent, Task

from optiflow.agents.codeblock import extract_code
from optiflow.agents.safety import check as safety_check
from optiflow.core.llm import llm_for
from optiflow.core.schemas import BuildResult, Candidate, TestResult
from optiflow.tools import compile as compile_tool
from optiflow.tools import verify as verify_tool

TOOL_NAMES = {"compile_code", "run_tests"}
MAX_SELF_REPAIR_TRIES = 2


def make_agent(tools) -> Agent:
    return Agent(
        role="Compiler and Executor",
        goal="Get the candidate to compile cleanly and pass every test case.",
        backstory=(
            "You fix C/C++ compile errors quickly and conservatively, changing "
            "only what's needed to make the code build, never the algorithm."
        ),
        tools=tools,
        llm=llm_for("compiler_exec", temperature=0.1),
        allow_delegation=False,
        max_iter=3,
        verbose=True,
    )


def run(agent: Agent, candidate: Candidate, lang: str, program_id: str) -> tuple[BuildResult, TestResult | None]:
    source = candidate.source
    build = compile_tool.compile_and_register(source, lang, "gcc", candidate.flags)

    tries = 0
    while not build.ok and tries < MAX_SELF_REPAIR_TRIES:
        tries += 1
        source = _self_repair(agent, source, build.stderr)
        is_safe, reason = safety_check(source)
        if not is_safe:
            break
        build = compile_tool.compile_and_register(source, lang, "gcc", candidate.flags)

    if not build.ok:
        return build, None

    tests = verify_tool.run_tests(build.candidate_id, program_id)
    return build, tests


def _self_repair(agent: Agent, source: str, stderr: str) -> str:
    task = Task(
        description=(
            "This C/C++ file fails to compile:\n\n"
            f"{source}\n\n"
            f"Compiler error (last 2000 chars):\n{stderr[-2000:]}\n\n"
            "Fix only what's needed to make it compile. Keep the algorithm "
            "and I/O format unchanged. Output the complete fixed file inside "
            "one fenced code block, no explanation."
        ),
        expected_output="A single fenced code block containing the fixed file.",
        agent=agent,
    )
    result = agent.kickoff([task]) if hasattr(agent, "kickoff") else task.execute_sync(agent)
    return extract_code(str(result))
