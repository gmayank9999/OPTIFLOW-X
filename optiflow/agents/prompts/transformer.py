"""Prompt template for the Code Transformer (Section 9.3)."""

TRANSFORM = """\
ORIGINAL SOURCE ({lang}):
{source}

APPLY THESE TRANSFORMATIONS: {strategies_json}

Constraints:
- Output the COMPLETE file inside one fenced code block. No explanation.
- Keep I/O format byte-identical. Keep all includes.
- Tiling must handle sizes not divisible by the tile (use min()).
- Do not add threads or OpenMP parallel directives (single-core comparison).
- Do not call system(), exec family, fork(), socket(), or inline asm.
"""

CRITIC_FEEDBACK_ADDENDUM = """\

PREVIOUS ATTEMPT FEEDBACK: {feedback}
Address this feedback in the new version.
"""
