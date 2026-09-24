"""Smoke test: the MCP server exposes exactly the seven tools from the plan,
and each one's underlying function actually works end to end."""

from optiflow.mcp_server import server

EXPECTED_TOOLS = {
    "get_program",
    "static_analysis",
    "compile_code",
    "run_tests",
    "run_benchmark",
    "profile_program",
    "compare_to_baseline",
}


def test_all_seven_tools_registered():
    names = {t.name for t in server.mcp._tool_manager.list_tools()}
    assert names == EXPECTED_TOOLS


def test_get_program_returns_source_and_meta():
    result = server.get_program("matmul_naive")
    assert "source" in result
    assert "int main" in result["source"]


def test_static_analysis_finds_loops():
    program = server.get_program("matmul_naive")
    result = server.static_analysis(program["source"], "c")
    assert result["features"]["max_loop_depth"] == 3.0


def test_compile_run_and_compare_round_trip():
    program = server.get_program("fib_recursive")
    build = server.compile_code(program["source"], "c", "gcc", ["-O2"])
    assert build["ok"]

    tests = server.run_tests(build["candidate_id"], "fib_recursive")
    assert tests["all_pass"]

    cmp = server.compare_to_baseline(build["candidate_id"], "fib_recursive", n=3)
    # identical source vs. itself: no real speedup expected
    assert 0.5 < cmp["speedup"] < 2.0
