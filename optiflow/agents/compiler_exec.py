"""Compiler & Executor agent.

Compiles the candidate through the compile_code MCP tool and runs the
correctness tests (outputs + exit status + sanitizers) through run_tests.
On a compile failure, gives the LLM the source and the last 2000
characters of stderr and asks for a fix, up to two tries. The repaired
source *replaces* the candidate's source, so whatever gets benchmarked and
possibly accepted is exactly the code that compiled.
"""

from __future__ import annotations

from crewai import Agent

from optiflow.agents.codeblock import extract_code, unified_diff
from optiflow.agents.common import make_agent as _make_agent
from optiflow.agents.mcp_tools import ToolClient
from optiflow.agents.prompts import transformer as prompts
from optiflow.agents.safety import check as safety_check
from optiflow.core import llm
from optiflow.core.schemas import BuildResult, Candidate, TestResult, TokenUsage

MAX_SELF_REPAIR_TRIES = 2


def make_agent(assignment: str | None = None) -> Agent:
    return _make_agent(
        "compiler_exec",
        title="Compiler and Executor",
        goal="Get the candidate to compile cleanly and pass every test case.",
        backstory=(
            "You fix C/C++ compile errors quickly and conservatively, changing "
            "only what's needed to make the code build, never the algorithm."
        ),
        assignment=assignment,
        temperature=0.1,
    )


def run(
    agent: Agent | None,
    tools: ToolClient,
    candidate: Candidate,
    parent_source: str,
    lang: str,
    program_id: str,
    allow_unsafe_math: bool = False,
) -> tuple[Candidate, BuildResult, TestResult | None, TokenUsage]:
    usage = TokenUsage()
    build = _compile(tools, candidate, lang, allow_unsafe_math)

    tries = 0
    while not build.ok and agent is not None and tries < MAX_SELF_REPAIR_TRIES:
        tries += 1
        try:
            text, u = llm.call(
                agent,
                prompts.REPAIR.format(lang=lang, source=candidate.source, stderr=build.stderr[-2000:]),
                "A single fenced code block containing the fixed file.",
            )
        except (llm.LLMCallError, llm.GuardrailFailed):
            break  # no repair available: the candidate is rejected with its compile error
        usage.add(u)
        fixed = extract_code(text)
        is_safe, _ = safety_check(fixed)
        if not is_safe:
            break
        candidate = candidate.model_copy(update={
            "source": fixed,
            "diff": unified_diff(parent_source, fixed),
            "repaired": tries,
        })
        build = _compile(tools, candidate, lang, allow_unsafe_math)

    if not build.ok:
        return candidate, build, None, usage

    tests = TestResult(**tools.call("run_tests", candidate_id=build.candidate_id, program_id=program_id))
    return candidate, build, tests, usage


def _compile(tools: ToolClient, candidate: Candidate, lang: str, allow_unsafe_math: bool) -> BuildResult:
    return BuildResult(**tools.call(
        "compile_code",
        source=candidate.source,
        lang=lang,
        compiler=candidate.compiler,
        flags=candidate.flags,
        allow_unsafe_math=allow_unsafe_math,
    ))
