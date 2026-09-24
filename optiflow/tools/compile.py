"""Compiles a candidate source file inside the sandbox.

Flags are whitelisted: an agent can propose flags, but it can never smuggle
arbitrary shell text into the compiler invocation.
"""

from __future__ import annotations

import pathlib
import tempfile
import uuid

from optiflow.core.schemas import BuildResult
from optiflow.tools.sandbox import run_in_sandbox

ALLOWED_FLAGS = {
    "-O0", "-O1", "-O2", "-O3", "-Ofast",
    "-march=native", "-mtune=native",
    "-funroll-loops", "-fopenmp-simd", "-flto",
    "-fno-math-errno", "-ftree-vectorize",
    "-g", "-lm",
}

# Excluded unless the caller explicitly opts in via compare="float_tol":
# -ffast-math reorders floating point operations and can change output.
UNSAFE_FOR_EXACT_COMPARE = {"-Ofast", "-ffast-math"}

_COMPILERS = {
    ("gcc", "c"): "gcc",
    ("gcc", "cpp"): "g++",
    ("clang", "c"): "clang",
    ("clang", "cpp"): "clang++",
}

# candidate_id -> {"dir": str, "binary": str}
_REGISTRY: dict[str, dict] = {}


def compile_and_register(
    source: str,
    lang: str = "c",
    compiler: str = "gcc",
    flags: list[str] | None = None,
) -> BuildResult:
    flags = [f for f in (flags or ["-O2"]) if f in ALLOWED_FLAGS]
    if not any(f.startswith("-O") for f in flags):
        flags.insert(0, "-O2")

    workdir = tempfile.mkdtemp(prefix="cand_")
    fname = "main.c" if lang == "c" else "main.cpp"
    pathlib.Path(workdir, fname).write_text(source)

    cc = _COMPILERS.get((compiler, lang), "gcc")
    flag_str = " ".join(f for f in flags if f != "-lm")
    link_libs = "-lm" if "-lm" in flags or True else ""
    result = run_in_sandbox(
        workdir,
        f"{cc} {flag_str} {fname} -o prog {link_libs}",
        timeout_s=60,
    )

    ok = result["exit"] == 0
    candidate_id = uuid.uuid4().hex if ok else None
    if ok:
        _REGISTRY[candidate_id] = {"dir": workdir, "binary": str(pathlib.Path(workdir, "prog"))}

    return BuildResult(
        ok=ok,
        stderr=result["stderr"][-4000:],
        binary_path=_REGISTRY[candidate_id]["binary"] if ok else None,
        candidate_id=candidate_id,
        compile_ms=result["wall_ms"],
    )


def get_candidate_dir(candidate_id: str) -> str:
    entry = _REGISTRY.get(candidate_id)
    if entry is None:
        raise KeyError(f"unknown candidate_id: {candidate_id}")
    return entry["dir"]
