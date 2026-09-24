"""Windows' default console codepage (cp1252) can't encode the emoji
CrewAI's logger writes on every tool/task event, which turns into a wall
of harmless-but-noisy encoding errors on stdout/stderr. Call this once
at process start on any entrypoint that runs agents interactively."""

from __future__ import annotations

import sys


def fix_windows_console_encoding() -> None:
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
