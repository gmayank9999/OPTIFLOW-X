"""Benchmark agent.

Times the candidate against the baseline through the compare_to_baseline
MCP tool: one interleaved session (baseline and candidate alternating in
the same container), so each candidate is measured exactly once and the
numbers the Critic acts on are the numbers that get reported. No LLM is
involved -- there is nothing for a model to decide here.
"""

from __future__ import annotations

from optiflow.agents.mcp_tools import ToolClient
from optiflow.core.schemas import CompareResult


def run(tools: ToolClient, candidate_id: str, program_id: str, n: int | None = None,
        reference_id: str | None = None) -> CompareResult:
    kwargs = {"candidate_id": candidate_id, "program_id": program_id}
    if n is not None:
        kwargs["n"] = n
    if reference_id:
        kwargs["reference_candidate_id"] = reference_id
    return CompareResult(**tools.call("compare_to_baseline", **kwargs))
