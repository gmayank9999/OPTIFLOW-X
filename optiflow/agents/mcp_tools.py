"""Shared MCP client wiring: every agent reaches the sandbox only through
the tool server in optiflow/mcp_server/server.py, never by calling the
tool functions directly. This keeps every architecture and every
messaging mode behind the same interface.
"""

from __future__ import annotations

import sys

from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "optiflow.mcp_server.server"],
)


def tool_subset(adapter_tools, names: set[str]) -> list:
    """Least-privilege selection: an agent only gets the tools it needs."""
    return [t for t in adapter_tools if t.name in names]
