"""Correctness checking: compares candidate output against reference output."""

from __future__ import annotations

import pathlib

from optiflow.core.schemas import TestResult
from optiflow.tools.compile import get_candidate_dir
from optiflow.tools.registry import _program_dir, load_meta
from optiflow.tools.sandbox import run_in_sandbox


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


def run_tests(candidate_id: str, program_id: str) -> TestResult:
    meta = load_meta(program_id)
    workdir = get_candidate_dir(candidate_id)
    program_dir = _program_dir(program_id)

    failed: list[str] = []
    details: dict = {}

    for in_rel, exp_rel in zip(meta["inputs"], meta["expected"]):
        in_path = program_dir / in_rel
        exp_path = program_dir / exp_rel
        expected = exp_path.read_text()

        actual = _run_with_input(workdir, in_path, meta.get("timeout_s", 20))

        matched = outputs_match(actual, expected, meta["compare"], meta.get("tolerance", 0.0))
        details[in_rel] = {"matched": matched, "actual_head": actual[:200]}
        if not matched:
            failed.append(in_rel)

    return TestResult(all_pass=len(failed) == 0, failed_cases=failed, details=details)


def _run_with_input(workdir: str, input_path: pathlib.Path, timeout_s: int) -> str:
    """Copies the input file into the candidate's workdir, then runs against it.

    Sandbox mounts only one host directory, so the input has to live inside
    that same workdir before the container can redirect stdin from it.
    """
    dest = pathlib.Path(workdir) / input_path.name
    if not dest.exists():
        dest.write_bytes(input_path.read_bytes())
    result = run_in_sandbox(workdir, f"./prog < {input_path.name}", timeout_s=timeout_s)
    return result["stdout"]
