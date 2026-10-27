"""Shared MCP client wiring: every agent reaches the sandbox only through
the tool server in optiflow/mcp_server/server.py.

`McpToolClient` holds one stdio session to the server for the whole run
and calls tools by name. Deterministic steps (fetching the program,
compiling, testing, benchmarking) call tools directly through this client;
LLM agents never get raw sandbox access. `DirectToolClient` has the same
interface but calls the tool functions in-process -- it exists for unit
tests of the orchestration logic, not for real runs.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AbstractContextManager

from mcp import StdioServerParameters
from pydantic import BaseModel, ValidationError

from optiflow.core.schemas import BenchResult, BuildResult, CompareResult, ProfileReport, TestResult

def server_params() -> StdioServerParameters:
    """The MCP SDK starts stdio servers with only a small whitelist of
    environment variables (PATH, HOME, ...). The tool server needs the
    parent's full configuration -- e.g. OPTIFLOW_WORKDIR, set by
    docker-compose rather than .env, decides where candidate builds live --
    so pass it through explicitly."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "optiflow.mcp_server.server"],
        env=dict(os.environ),
    )


SERVER_PARAMS = server_params()

TOOL_NAMES = (
    "get_program", "static_analysis", "compile_code", "run_tests",
    "run_benchmark", "profile_program", "compare_to_baseline",
)


class ToolError(RuntimeError):
    pass


class _ProgramRecord(BaseModel):
    program_id: str
    source: str
    meta: dict


class _AnalysisRecord(BaseModel):
    functions: list[str]
    loops: list[dict]
    features: dict[str, float]


# Expected shape of every tool's return value. Checked on *every* call,
# whatever the transport: a malformed (or tampered) tool result becomes a
# ToolError instead of flowing into an agent's prompt or the Critic.
TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_program": _ProgramRecord,
    "static_analysis": _AnalysisRecord,
    "compile_code": BuildResult,
    "run_tests": TestResult,
    "run_benchmark": BenchResult,
    "profile_program": ProfileReport,
    "compare_to_baseline": CompareResult,
}


def validate_tool_output(name: str, data) -> dict:
    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        raise ToolError(f"no output schema registered for tool {name!r}")
    if not isinstance(data, dict):
        raise ToolError(f"{name} returned {type(data).__name__}, expected an object")
    try:
        schema.model_validate(data)
    except ValidationError as exc:
        raise ToolError(f"{name} returned malformed data: {exc.errors()[:3]}") from exc
    return data


class ToolClient:
    transport = "abstract"

    def call(self, name: str, **kwargs) -> dict:
        return validate_tool_output(name, self._call(name, **kwargs))

    def _call(self, name: str, **kwargs):  # pragma: no cover - interface
        raise NotImplementedError


class McpToolClient(ToolClient, AbstractContextManager):
    transport = "mcp-stdio"

    def __init__(self) -> None:
        self._adapter = None
        self._tools: dict = {}

    def __enter__(self) -> "McpToolClient":
        from crewai_tools import MCPServerAdapter

        self._adapter = MCPServerAdapter(server_params())
        tools = self._adapter.__enter__()
        self._tools = {t.name: t for t in tools}
        missing = set(TOOL_NAMES) - set(self._tools)
        if missing:
            raise ToolError(f"MCP server is missing tools: {sorted(missing)}")
        return self

    def __exit__(self, *exc) -> None:
        if self._adapter is not None:
            self._adapter.__exit__(*exc)
            self._adapter = None

    def _call(self, name: str, **kwargs):
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool {name!r}")
        raw = tool.run(**kwargs)
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise ToolError(f"{name} failed: {str(raw)[:500]}") from exc


class DirectToolClient(ToolClient, AbstractContextManager):
    transport = "in-process"

    def __enter__(self) -> "DirectToolClient":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def _call(self, name: str, **kwargs):
        from optiflow.mcp_server import server

        fn = getattr(server, name, None)
        if fn is None or name not in TOOL_NAMES:
            raise ToolError(f"unknown tool {name!r}")
        return fn(**kwargs)
