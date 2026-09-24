"""The MCP tool server. Every agent, in every architecture, touches the
sandbox, the compiler and the benchmark only through these seven tools.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from optiflow.tools import analyze as analyze_tool
from optiflow.tools import bench as bench_tool
from optiflow.tools import compile as compile_tool
from optiflow.tools import profile as profile_tool
from optiflow.tools import registry
from optiflow.tools import verify as verify_tool

mcp = FastMCP("optiflow-tools")


@mcp.tool()
def get_program(program_id: str) -> dict:
    """Return source code and metadata of a benchmark program."""
    return registry.load(program_id)


@mcp.tool()
def static_analysis(source: str, lang: str = "c") -> dict:
    """Parse C/C++ with tree-sitter; return functions, loops and static features."""
    return analyze_tool.analyze(source, lang)


@mcp.tool()
def compile_code(
    source: str, lang: str = "c", compiler: str = "gcc", flags: list[str] | None = None
) -> dict:
    """Compile a candidate in the sandbox. Returns ok, stderr, candidate_id."""
    result = compile_tool.compile_and_register(source, lang, compiler, flags or ["-O2"])
    return result.model_dump()


@mcp.tool()
def run_tests(candidate_id: str, program_id: str) -> dict:
    """Run all test inputs for a candidate and compare against reference outputs."""
    result = verify_tool.run_tests(candidate_id, program_id)
    return result.model_dump()


@mcp.tool()
def run_benchmark(candidate_id: str, program_id: str, n: int = 10) -> dict:
    """Timed runs with warm-up; returns median/p95/std/cv/peak_mem."""
    result = bench_tool.run(candidate_id, program_id, n=n)
    return result.model_dump()


@mcp.tool()
def profile_program(program_id: str) -> dict:
    """Baseline profile: runtime, IPC, cache/branch miss rates, bottleneck summary."""
    result = profile_tool.profile(program_id)
    return result.model_dump()


@mcp.tool()
def compare_to_baseline(candidate_id: str, program_id: str, n: int = 10) -> dict:
    """Speedup vs baseline plus a Mann-Whitney significance test."""
    result = bench_tool.compare(candidate_id, program_id, n=n)
    return result.model_dump()


if __name__ == "__main__":
    mcp.run(transport="stdio")
