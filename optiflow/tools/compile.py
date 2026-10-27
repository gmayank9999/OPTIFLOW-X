"""Compiles a candidate source file inside the sandbox.

Flags are whitelisted: an agent can propose flags, but it can never smuggle
arbitrary shell text into the compiler invocation. Flags that reorder
floating-point math are only allowed when the program is compared with a
tolerance; for exact-output programs they are dropped (and reported back
in BuildResult.dropped_flags so the Strategist learns why).
"""

from __future__ import annotations

import pathlib
import shutil
import tempfile
import threading
import uuid
from collections import OrderedDict

from optiflow.core.schemas import BuildResult
from optiflow.tools.sandbox import run_in_sandbox

ALLOWED_FLAGS = {
    "-O0", "-O1", "-O2", "-O3", "-Ofast",
    "-march=native", "-mtune=native",
    "-funroll-loops", "-fopenmp-simd", "-flto",
    "-fno-math-errno", "-ftree-vectorize", "-ffast-math",
    "-fomit-frame-pointer", "-fno-plt",
    "-g", "-lm",
}

# -ffast-math / -Ofast reorder floating point operations and can change
# output in the last digits, so they're only safe under float_tol compare.
UNSAFE_FOR_EXACT_COMPARE = {"-Ofast", "-ffast-math"}

SANITIZER_FLAGS = ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]

_COMPILERS = {
    ("gcc", "c"): "gcc",
    ("gcc", "cpp"): "g++",
    ("clang", "c"): "clang",
    ("clang", "cpp"): "clang++",
}

# candidate_id -> {"dir", "binary", "flags", "source", "lang", "compiler"}
# Bounded: every build gets its own temp dir (with copies of the inputs),
# so the oldest unpinned candidates are deleted once MAX_CANDIDATES exist.
# Baselines are pinned because every comparison reuses them.
MAX_CANDIDATES = 96
_REGISTRY: "OrderedDict[str, dict]" = OrderedDict()
_PINNED: set[str] = set()
_registry_lock = threading.Lock()


def pin(candidate_id: str) -> None:
    _PINNED.add(candidate_id)


def _evict() -> None:
    while len(_REGISTRY) > MAX_CANDIDATES:
        victim = next((cid for cid in _REGISTRY if cid not in _PINNED), None)
        if victim is None:
            return
        entry = _REGISTRY.pop(victim)
        shutil.rmtree(entry["dir"], ignore_errors=True)


def sanitize_flags(flags: list[str] | None, allow_unsafe_math: bool = False) -> tuple[list[str], list[str]]:
    """Returns (kept, dropped). Keeps order, removes duplicates, guarantees an -O level."""
    kept: list[str] = []
    dropped: list[str] = []
    for flag in flags or ["-O2"]:
        flag = flag.strip()
        if flag not in ALLOWED_FLAGS or (flag in UNSAFE_FOR_EXACT_COMPARE and not allow_unsafe_math):
            dropped.append(flag)
        elif flag not in kept and flag != "-lm":
            kept.append(flag)
    if not any(f.startswith("-O") for f in kept):
        kept.insert(0, "-O2")
    return kept, dropped


def compile_and_register(
    source: str,
    lang: str = "c",
    compiler: str = "gcc",
    flags: list[str] | None = None,
    allow_unsafe_math: bool = False,
    sanitize: bool = False,
) -> BuildResult:
    if sanitize:
        kept, dropped = list(SANITIZER_FLAGS), []
    else:
        kept, dropped = sanitize_flags(flags, allow_unsafe_math)

    workdir = tempfile.mkdtemp(prefix="cand_")
    fname = "main.c" if lang == "c" else "main.cpp"
    pathlib.Path(workdir, fname).write_text(source, encoding="utf-8")

    cc = _COMPILERS.get((compiler, lang), "gcc")
    result = run_in_sandbox(
        workdir,
        f"{cc} {' '.join(kept)} {fname} -o prog -lm",
        timeout_s=60,
    )

    ok = result["exit"] == 0
    candidate_id = uuid.uuid4().hex if ok else None
    if not ok:
        stderr = result["stderr"][-4000:]
        shutil.rmtree(workdir, ignore_errors=True)
        return BuildResult(ok=False, stderr=stderr, compile_ms=result["wall_ms"], flags=kept, dropped_flags=dropped)
    with _registry_lock:
        _REGISTRY[candidate_id] = {
            "dir": workdir,
            "binary": str(pathlib.Path(workdir, "prog")),
            "flags": kept,
            "source": source,
            "lang": lang,
            "compiler": compiler,
        }
        binary = _REGISTRY[candidate_id]["binary"]
        _evict()

    return BuildResult(
        ok=True,
        stderr=result["stderr"][-4000:],
        binary_path=binary,
        candidate_id=candidate_id,
        compile_ms=result["wall_ms"],
        flags=kept,
        dropped_flags=dropped,
    )


def get_candidate_dir(candidate_id: str) -> str:
    entry = _REGISTRY.get(candidate_id)
    if entry is None:
        raise KeyError(f"unknown candidate_id: {candidate_id}")
    return entry["dir"]


def get_candidate(candidate_id: str) -> dict:
    entry = _REGISTRY.get(candidate_id)
    if entry is None:
        raise KeyError(f"unknown candidate_id: {candidate_id}")
    return entry
