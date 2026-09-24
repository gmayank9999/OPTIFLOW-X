"""Timed benchmarking with warm-up, repeated runs, and a baseline comparison.

Speedup claims are only trusted when they clear both a minimum margin and a
statistical significance test against the baseline's own run-to-run noise.
"""

from __future__ import annotations

import pathlib
import statistics

from scipy.stats import mannwhitneyu

from optiflow.core.schemas import BenchResult, CompareResult
from optiflow.tools.compile import compile_and_register, get_candidate_dir
from optiflow.tools.registry import _program_dir, load, load_meta
from optiflow.tools.sandbox import run_in_sandbox

CV_THRESHOLD = 0.05
MIN_SPEEDUP = 1.05
P_VALUE_THRESHOLD = 0.05

# program_id -> BenchResult, computed once per program per process.
_BASELINE_CACHE: dict[str, BenchResult] = {}


def run(candidate_id: str, program_id: str, n: int = 10, warmup: int = 2) -> BenchResult:
    meta = load_meta(program_id)
    workdir = get_candidate_dir(candidate_id)
    bench_input = _program_dir(program_id) / meta["bench_input"]
    timeout_s = meta.get("timeout_s", 20)

    dest = pathlib.Path(workdir) / bench_input.name
    if not dest.exists():
        dest.write_bytes(bench_input.read_bytes())

    cmd = (
        f"for i in $(seq {warmup + n}); do "
        f"/usr/bin/time -f \"%e %M\" -o /tmp/t -a ./prog < {bench_input.name} > /dev/null; "
        f"done; cat /tmp/t"
    )
    result = run_in_sandbox(workdir, cmd, timeout_s=timeout_s * (n + warmup) + 10)

    lines = [line.split() for line in result["stdout"].strip().splitlines()]
    timed_lines = lines[warmup:] if len(lines) >= warmup + n else lines
    runtimes_ms = [float(t) * 1000 for t, _ in timed_lines]
    peak_mem_kb = max((int(m) for _, m in timed_lines), default=0)

    return _summarize(runtimes_ms, peak_mem_kb)


def _summarize(runtimes_ms: list[float], peak_mem_kb: int) -> BenchResult:
    if not runtimes_ms:
        return BenchResult(
            runtimes_ms=[], median_ms=0, mean_ms=0, std_ms=0, p95_ms=0,
            cv=1.0, peak_mem_kb=peak_mem_kb, noisy=True,
        )
    mean = statistics.mean(runtimes_ms)
    std = statistics.stdev(runtimes_ms) if len(runtimes_ms) > 1 else 0.0
    cv = (std / mean) if mean else 0.0
    sorted_times = sorted(runtimes_ms)
    p95_idx = min(len(sorted_times) - 1, int(round(0.95 * (len(sorted_times) - 1))))
    return BenchResult(
        runtimes_ms=runtimes_ms,
        median_ms=statistics.median(runtimes_ms),
        mean_ms=mean,
        std_ms=std,
        p95_ms=sorted_times[p95_idx],
        cv=cv,
        peak_mem_kb=peak_mem_kb,
        noisy=cv > CV_THRESHOLD,
    )


def get_baseline(program_id: str, n: int = 10, warmup: int = 2) -> BenchResult:
    """Baseline: original source at -O2, benchmarked the same way, cached per program."""
    if program_id in _BASELINE_CACHE:
        return _BASELINE_CACHE[program_id]

    program = load(program_id)
    build = compile_and_register(program["source"], program["meta"]["language"], "gcc", ["-O2"])
    if not build.ok:
        raise RuntimeError(f"baseline failed to compile for {program_id}: {build.stderr}")

    result = run(build.candidate_id, program_id, n=n, warmup=warmup)
    _BASELINE_CACHE[program_id] = result
    return result


def compare(candidate_id: str, program_id: str, n: int = 10) -> CompareResult:
    baseline = get_baseline(program_id, n=n)
    candidate = run(candidate_id, program_id, n=n)

    if not candidate.runtimes_ms or not baseline.runtimes_ms:
        return CompareResult(speedup=0.0, p_value=1.0, accepted_by_rule=False)

    # /usr/bin/time has ~10ms resolution (Section 6.3), so a candidate
    # that's genuinely much faster than that can measure as exactly 0ms.
    # Treating that as a 0x speedup would silently reject the best
    # possible outcome; floor at a small epsilon instead so it reads as
    # "very fast" rather than "instant and therefore invalid".
    candidate_ms = max(candidate.median_ms, 1.0)
    speedup = baseline.median_ms / candidate_ms
    try:
        _, p_value = mannwhitneyu(
            baseline.runtimes_ms, candidate.runtimes_ms, alternative="greater"
        )
    except ValueError:
        p_value = 1.0

    accepted = speedup >= MIN_SPEEDUP and p_value < P_VALUE_THRESHOLD
    return CompareResult(speedup=speedup, p_value=float(p_value), accepted_by_rule=accepted)
