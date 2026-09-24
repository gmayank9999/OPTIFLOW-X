"""Extracts a fenced code block from an LLM response and diffs it against
the original source. Pure text processing, no LLM calls."""

from __future__ import annotations

import difflib
import re

_FENCE_RE = re.compile(r"```(?:\w+)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    """Pulls the first fenced code block out of an LLM response.

    Falls back to the raw text when no fence is present, since some
    models omit the backticks despite being asked for them.
    """
    match = _FENCE_RE.search(text)
    return match.group(1).rstrip("\n") + "\n" if match else text.strip() + "\n"


def unified_diff(original: str, updated: str, filename: str = "main.c") -> str:
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff_lines)
