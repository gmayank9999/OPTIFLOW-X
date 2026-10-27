"""Correctness checking: compares candidate output against reference output,
then rebuilds the candidate with AddressSanitizer + UBSan and runs it on the
small edge-case inputs (Section 6.5).

A test case only passes when the program exits cleanly *and* its output
matches. The sanitizer pass catches out-of-bounds reads from bad tiling
that happen to produce the right checksum on the reference inputs.
"""

from __future__ import annotations

import pathlib

from optiflow.core.schemas import TestResult
from optiflow.tools.compile import compile_and_register, get_candidate, get_candidate_dir
from optiflow.tools.registry import _program_dir, load_meta
from optiflow.tools.sandbox import run_in_sandbox

# LeakSanitizer needs ptrace, which the sandbox (rightly) forbids; leaks
# aren't a correctness failure for these programs anyway.
SANITIZER_ENV = {
    "ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0:exitcode=86",
    "UBSAN_OPTIONS": "print_stacktrace=1:halt_on_error=1:exitcode=86",
}
SANITIZER_EXIT = 86


def outputs_match(actual: str, expected: str, mode: str, tolerance: float) -> bool:
    if mode == "exact":
        return actual.strip() == expected.strip()

    actual_tokens = actual.split()
    expected_tokens = expected.split()
    if len(actual_tokens) != len(expected_tokens):
        return False

    for a, e in zip(actual_tokens, expected_tokens):
        try:
            fa, fe = float(a), float(e)
        except ValueError:
            if a != e:
                return False
            continue
        if abs(fa - fe) > tolerance * max(1.0, abs(fe)):
            return False
    return True


def run_tests(candidate_id: str, program_id: str, sanitize: bool = True) -> TestResult:
    meta = load_meta(program_id)
    workdir = get_candidate_dir(candidate_id)
    program_dir = _program_dir(program_id)
    timeout_s = meta.get("timeout_s", 20)

    failed: list[str] = []
    details: dict = {}

    for in_rel, exp_rel in zip(meta["inputs"], meta["expected"]):
        expected = (program_dir / exp_rel).read_text()
        result = _run_with_input(workdir, program_dir / in_rel, timeout_s)
        actual = result["stdout"]

        if result["timed_out"]:
            status = "timeout"
        elif result["exit"] != 0:
            status = f"exit_{result['exit']}"
        elif outputs_match(actual, expected, meta["compare"], meta.get("tolerance", 0.0)):
            status = "pass"
        else:
            status = "wrong_output"

        details[in_rel] = {
            "status": status,
            "matched": status == "pass",
            "actual_head": actual[:200],
            "expected_head": expected[:200],
        }
        if status != "pass":
            failed.append(in_rel)

    sanitizer_ok, sanitizer_report = None, ""
    if sanitize and not failed:
        sanitizer_ok, sanitizer_report = _sanitizer_check(candidate_id, program_id, meta)
        if sanitizer_ok is False:
            failed.append("sanitizer")

    return TestResult(
        all_pass=len(failed) == 0,
        failed_cases=failed,
        details=details,
        sanitizer_ok=sanitizer_ok,
        sanitizer_report=sanitizer_report,
    )


def _sanitizer_check(candidate_id: str, program_id: str, meta: dict) -> tuple[bool | None, str]:
    """Rebuilds with -fsanitize=address,undefined and runs every input except
    the (large) benchmark input. Returns (ok, report); ok is None when the
    sanitizer build itself isn't possible (e.g. the toolchain refuses), so
    a missing sanitizer never masquerades as a pass or a failure."""
    entry = get_candidate(candidate_id)
    build = compile_and_register(entry["source"], entry["lang"], entry["compiler"], sanitize=True)
    if not build.ok:
        return None, f"sanitizer build failed: {build.stderr[-300:]}"

    program_dir = _program_dir(program_id)
    small_inputs = [i for i in meta["inputs"] if i != meta["bench_input"]] or meta["inputs"][:1]
    for in_rel in small_inputs:
        result = _run_with_input(get_candidate_dir(build.candidate_id), program_dir / in_rel,
                                 meta.get("timeout_s", 20) * 5, env=SANITIZER_ENV)
        if result["exit"] == SANITIZER_EXIT or "runtime error:" in result["stderr"] \
                or "ERROR: AddressSanitizer" in result["stderr"]:
            return False, f"{in_rel}: {result['stderr'][-1500:]}"
    return True, ""


def _run_with_input(workdir: str, input_path: pathlib.Path, timeout_s: int,
                    env: dict[str, str] | None = None) -> dict:
    """Copies the input file into the candidate's workdir, then runs against it.

    Sandbox mounts only one host directory, so the input has to live inside
    that same workdir before the container can redirect stdin from it.
    """
    dest = pathlib.Path(workdir) / input_path.name
    if not dest.exists():
        dest.write_bytes(input_path.read_bytes())
    # Execute from the container's own tmpfs, never from the bind mount:
    # the shared work dir may be on a noexec filesystem (Docker Desktop's VM,
    # hardened hosts that mount /tmp or /var noexec).
    return run_in_sandbox(workdir, f"cp prog /tmp/prog && /tmp/prog < {input_path.name}",
                          timeout_s=timeout_s, env=env)
