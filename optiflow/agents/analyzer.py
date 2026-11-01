"""Program Analyzer agent.

Fetches the program and its static analysis through the MCP tools
(get_program, static_analysis), then asks the LLM for a short structural
summary. The loops/functions/features themselves come straight from
tree-sitter, not from the model, so a bad summary can never corrupt the
data the rest of the pipeline reasons over.
"""

from __future__ import annotations

import json

from crewai import Agent

from optiflow.agents.common import make_agent as _make_agent
from optiflow.agents.common import numbered
from optiflow.agents.mcp_tools import ToolClient
from optiflow.core import llm
from optiflow.core.schemas import ProgramSummary, TokenUsage
from optiflow.security.guardrails import check_llm_output, sanitize_source


def make_agent(assignment: str | None = None) -> Agent:
    return _make_agent(
        "analyzer",
        title="Program Analyzer",
        goal="Extract an accurate structural summary of the target C/C++ program.",
        backstory=(
            "You read unfamiliar C/C++ source quickly and describe its structure "
            "precisely: what the hot loops do, what they touch in memory, and "
            "which function they live in."
        ),
        assignment=assignment,
        temperature=0.1,
    )


def run(agent: Agent | None, tools: ToolClient, program_id: str) -> tuple[ProgramSummary, TokenUsage]:
    program = tools.call("get_program", program_id=program_id)
    lang = program["meta"]["language"]
    # Untrusted input: injection attempts hidden in comments are neutralized
    # before any model reads the code. Comments don't change semantics, so
    # this sanitized source is what every agent works from.
    guard = sanitize_source(program["source"])
    source = guard.sanitized
    analysis = tools.call("static_analysis", source=source, lang=lang)

    usage = TokenUsage()
    if agent is None:
        summary_text = deterministic_summary(analysis)
    else:
        loops = [
            {k: loop[k] for k in ("function", "line", "end_line", "depth", "iter_vars", "array_accesses")}
            for loop in analysis["loops"]
        ]
        try:
            summary_text, usage = llm.call(
                agent,
                description=(
                    f"PROGRAM {program_id} ({lang}):\n{numbered(source)}\n\n"
                    f"LOOPS (from tree-sitter): {json.dumps(loops)}\n"
                    f"STATIC FEATURES: {json.dumps(analysis['features'])}\n\n"
                    "Write a 3-5 line plain-text summary of this program's structure: what "
                    "it computes, which loop nest is likely hottest (cite line numbers), and "
                    "any cache-unfriendly access pattern, redundant work, or algorithmic "
                    "inefficiency. No code, no markdown."
                ),
                expected_output="A short structural summary, 3-5 lines, plain text.",
                guardrail=_clean_text,
            )
        except (llm.GuardrailFailed, llm.LLMCallError):
            summary_text = deterministic_summary(analysis)  # never pass flagged text onward

    return ProgramSummary(
        program_id=program_id,
        language=lang,
        source=source,
        functions=analysis["functions"],
        loops=analysis["loops"],
        features=analysis["features"],
        summary_text=summary_text.strip(),
        guardrail_findings=[f.__dict__ for f in guard.findings],
    ), usage


def _clean_text(text: str) -> tuple[bool, str]:
    result = check_llm_output(text, "analyzer_summary")
    return result.ok, result.summary()


def deterministic_summary(analysis: dict) -> str:
    f = analysis["features"]
    notes = [f"{int(f['n_loops'])} loops, max nesting depth {int(f['max_loop_depth'])}"]
    for key, text in (
        ("stride_mismatch", "an innermost loop walks a non-contiguous dimension"),
        ("has_recursion", "recursive function(s)"),
        ("has_struct_array", "array-of-structs accessed field by field"),
        ("strlen_in_loop_cond", "strlen() evaluated in a loop condition"),
        ("pointer_chasing", "linked-structure traversal"),
    ):
        if f.get(key):
            notes.append(text)
    return "; ".join(notes) + "."
