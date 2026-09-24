"""Benchmark agent.

Times the candidate and compares it to the baseline. The LLM's role here
is limited to phrasing the result for the trace/dashboard; the numbers
the Critic acts on come straight from bench.py.
"""

from __future__ import annotations

from optiflow.core.schemas import BenchResult, CompareResult
from optiflow.tools import bench as bench_tool


def run(candidate_id: str, program_id: str, n: int = 10) -> tuple[BenchResult, CompareResult]:
    result = bench_tool.run(candidate_id, program_id, n=n)
    comparison = bench_tool.compare(candidate_id, program_id, n=n)
    return result, comparison
