"""User-submitted programs (the workspace's "Paste my code" / upload flow).

The benchmark suite ships hand-made inputs and expected outputs. For a
program the user brings, the *reference* is the user's own original code:
it is compiled at -O2 in the sandbox and run on each test input, and those
outputs become the expected files. A candidate is then accepted only if it
reproduces them, so "correct" always means "same output as your original on
the inputs you gave" -- nothing stronger, and the UI says so.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import uuid

from optiflow.tools import registry

MAX_SOURCE_BYTES = 256 * 1024
MAX_INPUT_BYTES = 1024 * 1024
MAX_INPUTS = 3
TIMEOUT_S = 10


class CustomProgramError(ValueError):
    """The submitted program can't be used; the message is shown to the user."""


def new_program_id() -> str:
    return f"{registry.CUSTOM_PREFIX}{uuid.uuid4().hex[:12]}"


def validate_submission(source: str, language: str, test_inputs: list[str]) -> None:
    """Cheap checks that need no Docker; run before a job is queued."""
    if language not in ("c", "cpp"):
        raise CustomProgramError("language must be 'c' or 'cpp'")
    if not source.strip():
        raise CustomProgramError("The code is empty. Paste or upload a C/C++ program first.")
    if len(source.encode()) > MAX_SOURCE_BYTES:
        raise CustomProgramError(f"The code is larger than {MAX_SOURCE_BYTES // 1024} KB.")
    if "main" not in source:
        raise CustomProgramError("No main() function found. The program must be a complete, runnable file.")
    if len(test_inputs) > MAX_INPUTS:
        raise CustomProgramError(f"At most {MAX_INPUTS} test inputs are supported.")
    for i, text in enumerate(test_inputs, 1):
        if len(text.encode()) > MAX_INPUT_BYTES:
            raise CustomProgramError(f"Test input {i} is larger than {MAX_INPUT_BYTES // 1024} KB.")


_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_RANDOM_OR_TIME = re.compile(
    r"\b(rand|srand|random|srandom|drand48|time|clock|clock_gettime|gettimeofday|getpid|random_device|chrono)\b")
_READS_INPUT = re.compile(r"\b(scanf|fscanf|sscanf|cin|fgets|getchar|getline|fread|gets|getc|read)\b")
_THREADS = re.compile(r"\b(pthread_create|std::thread|std::async)\b|#\s*pragma\s+omp")


def explain_nondeterminism(source: str, language: str, label: str, stdin_text: str,
                           out1: str, out2: str) -> str:
    """Why two runs of the same program on the same input printed different
    output, in terms the user can act on. This only explains: the run is
    still rejected, because an unstable reference can't verify anything."""
    a, b = out1.splitlines(), out2.splitlines()
    n = next((i for i in range(max(len(a), len(b)))
              if (a[i] if i < len(a) else None) != (b[i] if i < len(b) else None)), 0)

    def clip(lines: list[str]) -> str:
        return lines[n][:80] if n < len(lines) else "(no line)"

    code = _COMMENTS.sub(" ", source)
    causes: list[str] = []
    if _RANDOM_OR_TIME.search(code):
        causes.append("It uses random numbers, the clock or the process id (rand/srand/time/clock/getpid...). "
                      "Their values change on every run.")
    if "%p" in code:
        causes.append("It prints a memory address (%p). Addresses are randomised on every run.")
    if _THREADS.search(code):
        causes.append("It uses threads/OpenMP. If threads print or update shared data in an unpredictable "
                      "order, the output changes between runs.")
    if _READS_INPUT.search(code) and not stdin_text.strip():
        causes.append("It reads input, but no example input was given, so the read fails and the variables "
                      "it should have filled keep random leftover memory. This is the most common cause: "
                      "add an example input in step 1 (\"Does your program read input?\").")
    if not causes:
        causes.append("Nothing in the source explains it, so the usual suspect is a variable or array that is "
                      "used before it is set (uninitialised memory), or a data race.")

    compiler = "gcc" if language == "c" else "g++"
    fixes = [
        "Give every variable and array a value before it is used (int x = 0; use calloc or memset).",
        "Check that reads such as scanf succeeded: if (scanf(\"%d\", &n) != 1) return 1;",
        "Seed random numbers with a fixed value (srand(42)) and don't print times or addresses.",
        f"To find the problem yourself, compile with: {compiler} -O2 -Wall -Wextra -Wuninitialized",
    ]
    return (
        f"Your original code printed different output on two identical runs of {label}, so we can't tell "
        "whether an optimized version is still correct. Verification needs the same input to always give the "
        "same output, so this program can't be optimized as it is.\n\n"
        f"First difference (output line {n + 1}):\n  run 1: {clip(a)}\n  run 2: {clip(b)}\n\n"
        "Likely cause:\n" + "\n".join(f"  • {c}" for c in causes)
        + "\n\nHow to fix it:\n" + "\n".join(f"  • {f}" for f in fixes)
    )


def materialize(program_id: str, source: str, language: str, test_inputs: list[str]) -> dict:
    """Writes the program to disk and generates expected outputs by running
    the original in the sandbox. Needs Docker. Returns the meta dict."""
    from optiflow.tools.compile import compile_and_register, get_candidate_dir
    from optiflow.tools.verify import _run_with_input

    validate_submission(source, language, test_inputs)
    inputs = [t for t in test_inputs if t is not None] or [""]  # no input -> program reads empty stdin

    root = registry.CUSTOM_ROOT / program_id
    try:
        (root / "inputs").mkdir(parents=True)
        (root / "expected").mkdir()
        (root / ("main.c" if language == "c" else "main.cpp")).write_text(source, encoding="utf-8")

        build = compile_and_register(source, language, "gcc", ["-O2"])
        if not build.ok:
            raise CustomProgramError("Your original code does not compile:\n" + build.stderr.strip()[-1500:])
        workdir = get_candidate_dir(build.candidate_id)

        in_rel, exp_rel, sizes = [], [], []
        for i, text in enumerate(inputs, 1):
            in_path = root / "inputs" / f"in{i}.txt"
            in_path.write_text(text, encoding="utf-8")
            first = _run_with_input(workdir, in_path, TIMEOUT_S)
            label = f"test input {i}" if len(inputs) > 1 else "your program"
            if first["timed_out"]:
                raise CustomProgramError(f"Your original code timed out (>{TIMEOUT_S}s) on {label}.")
            if first["exit"] != 0:
                raise CustomProgramError(
                    f"Your original code exited with status {first['exit']} on {label}. "
                    "It must run cleanly (return 0) so its output can be used as the reference."
                    + (f"\n{first['stderr'].strip()[-400:]}" if first["stderr"].strip() else ""))
            second = _run_with_input(workdir, in_path, TIMEOUT_S)
            if second["stdout"] != first["stdout"]:
                raise CustomProgramError(explain_nondeterminism(
                    source, language, label, text, first["stdout"], second["stdout"]))
            out_path = root / "expected" / f"out{i}.txt"
            out_path.write_text(first["stdout"], encoding="utf-8")
            in_rel.append(f"inputs/in{i}.txt")
            exp_rel.append(f"expected/out{i}.txt")
            sizes.append(len(text))

        meta = {
            "id": program_id, "category": "custom", "language": language,
            "inputs": in_rel, "expected": exp_rel,
            # The largest input is the one that gets timed.
            "bench_input": in_rel[sizes.index(max(sizes))],
            "compare": "exact", "tolerance": 0, "timeout_s": TIMEOUT_S, "subset10": False,
        }
        (root / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
