"""The MCP tool server. Every agent, in every architecture, touches the
sandbox, the compiler and the benchmark only through these seven tools.

The candidate registry (candidate_id -> build directory) lives in this
process, so binaries never pass through an LLM or across the protocol --
only ids do.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from optiflow.tools import analyze as analyze_tool
from optiflow.tools import bench as bench_tool
from optiflow.tools import compile as compile_tool
from optiflow.tools import profile as profile_tool
from optiflow.tools import registry
from optiflow.tools import verify as verify_tool

mcp = FastMCP("optiflow-tools", log_level="WARNING")


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
    source: str,
    lang: str = "c",
    compiler: str = "gcc",
    flags: list[str] | None = None,
    allow_unsafe_math: bool = False,
) -> dict:
    """Compile a candidate in the sandbox. Returns ok, stderr, candidate_id, kept/dropped flags."""
    result = compile_tool.compile_and_register(
        source, lang, compiler, flags or ["-O2"], allow_unsafe_math=allow_unsafe_math
    )
    return result.model_dump()


@mcp.tool()
def run_tests(candidate_id: str, program_id: str, sanitize: bool = True) -> dict:
    """Run all test inputs (exit status + output) and an ASan/UBSan pass on the small inputs."""
    result = verify_tool.run_tests(candidate_id, program_id, sanitize=sanitize)
    return result.model_dump()


@mcp.tool()
def run_benchmark(candidate_id: str, program_id: str, n: int = 10) -> dict:
    """Timed runs with warm-up; returns median/p95/std/cv/cpu time/peak_mem."""
    result = bench_tool.run(candidate_id, program_id, n=n)
    return result.model_dump()


@mcp.tool()
def profile_program(program_id: str) -> dict:
    """Baseline profile: runtime, IPC, cache/branch miss rates, loop hotspots."""
    result = profile_tool.profile(program_id)
    return result.model_dump()


@mcp.tool()
def compare_to_baseline(candidate_id: str, program_id: str, n: int = 0, reference_candidate_id: str = "") -> dict:
    """Interleaved baseline-vs-candidate timing; speedup plus a Mann-Whitney p-value.
    n=0 picks the repetition count adaptively from the stability table.
    reference_candidate_id (the current best) is timed in the same session and
    tested against the candidate too."""
    result = bench_tool.compare(candidate_id, program_id, n=n or None, reference_id=reference_candidate_id or None)
    return result.model_dump()


if __name__ == "__main__":
    mcp.run(transport="stdio")
