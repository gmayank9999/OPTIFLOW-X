"""Pre-compile safety filter for LLM-generated candidate source.

Cheap regex checks that reject anything trying to reach outside the
sandbox's own guarantees. This runs before compile_code, on every
candidate, in every architecture.
"""

from __future__ import annotations

import re

_FORBIDDEN_PATTERNS = [
    re.compile(r"\bsystem\s*\("),
    re.compile(r"\bpopen\s*\("),
    re.compile(r"\bfork\s*\("),
    re.compile(r"\bvfork\s*\("),
    re.compile(r"\bexecv?[ep]?\s*\("),
    re.compile(r"\bsocket\s*\("),
    re.compile(r"\basm\s*(volatile)?\s*\("),
    re.compile(r"\b__asm__\s*\("),
    re.compile(r'\bfopen\s*\(\s*"/(?!work)'),
    re.compile(r"\bdlopen\s*\("),
]


def check(source: str) -> tuple[bool, str | None]:
    """Returns (is_safe, reason). reason is None when safe."""
    for pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(source)
        if match:
            return False, f"forbidden call: {match.group(0).strip()}"
    return True, None
