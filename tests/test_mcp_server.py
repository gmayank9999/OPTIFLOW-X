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


def test_tools_work_over_the_real_stdio_protocol():
    """The agents' path: a separate server process, JSON over stdio."""
    from optiflow.agents.mcp_tools import McpToolClient

    with McpToolClient() as tools:
        program = tools.call("get_program", program_id="fib_recursive")
        analysis = tools.call("static_analysis", source=program["source"], lang="c")
        assert analysis["features"]["has_recursion"] == 1.0
        build = tools.call("compile_code", source=program["source"], flags=["-O2", "-Ofast"])
        assert build["ok"] and build["dropped_flags"] == ["-Ofast"]  # exact-compare program
        tests = tools.call("run_tests", candidate_id=build["candidate_id"], program_id="fib_recursive")
        assert tests["all_pass"] and tests["sanitizer_ok"] is True


def test_tool_server_inherits_the_full_environment(monkeypatch):
    """Regression: the MCP SDK's default whitelist dropped OPTIFLOW_WORKDIR,
    so in docker-compose the tool server built candidates where the host's
    Docker daemon couldn't see them."""
    from optiflow.agents.mcp_tools import server_params

    monkeypatch.setenv("OPTIFLOW_WORKDIR", "/var/optiflow/work")
    assert server_params().env["OPTIFLOW_WORKDIR"] == "/var/optiflow/work"
