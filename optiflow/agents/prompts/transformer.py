"""Prompt templates for the Code Transformer (Section 9.3) and the
Compiler & Executor's self-repair step (Section 9.4)."""

TRANSFORM = """\
ORIGINAL SOURCE ({lang}):
```{lang}
{source}
```

APPLY THESE TRANSFORMATIONS: {strategies_json}

Constraints:
- Output the COMPLETE file inside one fenced code block. No explanation.
- Output must be {compare_rule}. Keep the I/O format byte-identical. Keep all includes.
- Tiling must handle sizes not divisible by the tile (use min()); inputs include n=1 and n=33.
- Do not add threads or OpenMP parallel directives (single-core comparison).
- Do not call system(), exec family, fork(), socket(), or inline asm; read only stdin.
"""

CRITIC_FEEDBACK_ADDENDUM = """\

THE PREVIOUS VERSION OF THIS TRANSFORMATION WAS REJECTED: {feedback}
Fix that problem in this version.
"""

REPAIR = """\
This {lang} file fails to compile:

```{lang}
{source}
```

Compiler error (last 2000 chars):
{stderr}

Fix only what's needed to make it compile. Keep the algorithm and I/O format
unchanged. Output the complete fixed file inside one fenced code block, no explanation.
"""
