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
import sys
from contextlib import AbstractContextManager

from mcp import StdioServerParameters

SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "optiflow.mcp_server.server"],
)

TOOL_NAMES = (
    "get_program", "static_analysis", "compile_code", "run_tests",
    "run_benchmark", "profile_program", "compare_to_baseline",
)


class ToolError(RuntimeError):
    pass


class ToolClient:
    transport = "abstract"

    def call(self, name: str, **kwargs) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class McpToolClient(ToolClient, AbstractContextManager):
    transport = "mcp-stdio"

    def __init__(self) -> None:
        self._adapter = None
        self._tools: dict = {}

    def __enter__(self) -> "McpToolClient":
        from crewai_tools import MCPServerAdapter

        self._adapter = MCPServerAdapter(SERVER_PARAMS)
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

    def call(self, name: str, **kwargs) -> dict:
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

    def call(self, name: str, **kwargs) -> dict:
        from optiflow.mcp_server import server

        fn = getattr(server, name, None)
        if fn is None or name not in TOOL_NAMES:
            raise ToolError(f"unknown tool {name!r}")
        return fn(**kwargs)
