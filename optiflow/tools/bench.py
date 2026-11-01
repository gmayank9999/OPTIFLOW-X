"""Timed benchmarking with warm-up, repeated runs, and a baseline comparison.

Timing uses the `hrtime` harness baked into the sandbox image
(docker/hrtime.c): CLOCK_MONOTONIC wall time with nanosecond resolution,
plus CPU time and peak RSS from wait4(). /usr/bin/time's 10 ms resolution
was too coarse to compare fast candidates honestly.

A comparison runs baseline and candidate *interleaved in the same
container* (A B A B ...), so slow drift on the host affects both equally
instead of biasing whichever ran second (Section 6.3, "same session").
Speedup claims are only trusted when they clear both a minimum margin and
a one-sided Mann-Whitney U test.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import statistics

from scipy.stats import mannwhitneyu

from optiflow.core.schemas import BenchResult, CompareResult
from optiflow.tools.compile import compile_and_register, get_candidate_dir, pin
from optiflow.tools.registry import _program_dir, load, load_meta
from optiflow.tools.sandbox import run_in_sandbox

CV_THRESHOLD = 0.05
MIN_SPEEDUP = 1.05
P_VALUE_THRESHOLD = 0.05
DEFAULT_RUNS = 10
DEFAULT_WARMUP = 2
LOW_PRECISION_MS = 20.0     # below this, process start-up dominates the measurement
LOW_PRECISION_CV = 0.25     # above this, medians of 10-30 runs are not a precise ratio
MAX_ADAPTIVE_RUNS = 30
ADAPTIVE_BUDGET_MS = 8000  # target time spent on timed baseline runs per comparison
STABILITY_PATH = pathlib.Path("results/stability.json")

# program_id -> candidate_id of the original source built at -O2.
_BASELINE_BUILDS: dict[str, str] = {}
# program_id -> standalone baseline BenchResult (used by the profiler).
_BASELINE_CACHE: dict[str, BenchResult] = {}


def _stage_input(workdir: str, program_id: str) -> str:
    meta = load_meta(program_id)
    bench_input = _program_dir(program_id) / meta["bench_input"]
    dest = pathlib.Path(workdir) / bench_input.name
    if not dest.exists():
        dest.write_bytes(bench_input.read_bytes())
    return bench_input.name


def _run_harness(workdir: str, programs: list[str], input_name: str, n: int, warmup: int,
                 timeout_s: int) -> list[list[tuple[float, float, int, int]]]:
    """Returns, per program, a list of (wall_ms, cpu_ms, maxrss_kb, exit_status)."""
    # Stage binaries and input in the container's tmpfs, then time from
    # there: no host-filesystem I/O inside the measured region.
    files = " ".join([*programs, input_name])
    cmd = (f"cp {files} /tmp/ && cd /tmp && "
           f"hrtime {n} {warmup} {input_name} " + " ".join(f"./{p}" for p in programs))
    total_timeout = timeout_s * (n + warmup) * len(programs) + 15
    result = run_in_sandbox(workdir, cmd, timeout_s=total_timeout)

    per_prog: list[list[tuple[float, float, int, int]]] = [[] for _ in programs]
    for line in result["stdout"].splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        idx, wall, cpu, rss, status = int(parts[0]), float(parts[1]), float(parts[2]), int(parts[3]), int(parts[4])
        if 0 <= idx < len(programs):
            per_prog[idx].append((wall, cpu, rss, status))
    return per_prog


def summarize(samples: list[tuple[float, float, int, int]]) -> BenchResult:
    ok = [s for s in samples if s[3] == 0]
    failed = len(samples) - len(ok)
    if not ok:
        return BenchResult(
            runtimes_ms=[], median_ms=0, mean_ms=0, std_ms=0, p95_ms=0,
            cv=1.0, peak_mem_kb=0, noisy=True, failed_runs=failed,
        )
    runtimes_ms = [s[0] for s in ok]
    cpu_ms = [s[1] for s in ok]
    cpu_mean = statistics.mean(cpu_ms)
    cpu_cv = (statistics.stdev(cpu_ms) / cpu_mean) if len(cpu_ms) > 1 and cpu_mean else 0.0
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
        peak_mem_kb=max(s[2] for s in ok),
        cpu_median_ms=statistics.median(cpu_ms),
        cpu_runtimes_ms=cpu_ms,
        cpu_cv=cpu_cv,
        noisy=cv > CV_THRESHOLD,
        failed_runs=failed,
    )


def run(candidate_id: str, program_id: str, n: int = DEFAULT_RUNS, warmup: int = DEFAULT_WARMUP) -> BenchResult:
    """Benchmark one candidate on its own (no baseline interleaving)."""
    workdir = get_candidate_dir(candidate_id)
    input_name = _stage_input(workdir, program_id)
    timeout_s = load_meta(program_id).get("timeout_s", 20)
    samples = _run_harness(workdir, ["prog"], input_name, n, warmup, timeout_s)[0]
    result = summarize(samples)
    if result.noisy and result.runtimes_ms:
        # Section 6.3 step 5: rerun once when CV > 5%; keep it flagged if still noisy.
        retry = summarize(_run_harness(workdir, ["prog"], input_name, n, warmup, timeout_s)[0])
        if retry.cv < result.cv:
            result = retry
    return result


def baseline_candidate(program_id: str) -> str:
    """candidate_id of the original program built at -O2 (built once per process)."""
    if program_id not in _BASELINE_BUILDS:
        program = load(program_id)
        build = compile_and_register(program["source"], program["meta"]["language"], "gcc", ["-O2"])
        if not build.ok:
            raise RuntimeError(f"baseline failed to compile for {program_id}: {build.stderr}")
        pin(build.candidate_id)
        _BASELINE_BUILDS[program_id] = build.candidate_id
    return _BASELINE_BUILDS[program_id]


def get_baseline(program_id: str, n: int = DEFAULT_RUNS, warmup: int = DEFAULT_WARMUP) -> BenchResult:
    """Standalone baseline measurement, cached per program per process."""
    if program_id not in _BASELINE_CACHE:
        _BASELINE_CACHE[program_id] = run(baseline_candidate(program_id), program_id, n=n, warmup=warmup)
    return _BASELINE_CACHE[program_id]


def adaptive_runs(program_id: str) -> int:
    """Short programs are noisier relative to their runtime, so they get
    more repetitions: enough timed baseline runs to fill ~8 s, between 10
    and 30. Uses the stability table's median; 10 if it isn't there."""
    try:
        median = json.loads(STABILITY_PATH.read_text())["programs"][program_id]["median_ms"]
    except (OSError, KeyError, ValueError):
        return DEFAULT_RUNS
    if median <= 0:
        return DEFAULT_RUNS
    return max(DEFAULT_RUNS, min(MAX_ADAPTIVE_RUNS, int(ADAPTIVE_BUDGET_MS / median)))


def compare(candidate_id: str, program_id: str, n: int | None = None, warmup: int = DEFAULT_WARMUP,
            reference_id: str | None = None) -> CompareResult:
    """Interleaved baseline-vs-candidate measurement in one container.
    With `reference_id` (the current best candidate) the reference is timed
    in the same session too, so "better than the best so far" is a
    statistical statement rather than a comparison of two point estimates."""
    return compare_many([candidate_id], program_id, n=n, warmup=warmup, reference_id=reference_id)[0]


def compare_many(candidate_ids: list[str], program_id: str, n: int | None = None,
                 warmup: int = DEFAULT_WARMUP, reference_id: str | None = None) -> list[CompareResult]:
    """Baseline and every candidate interleaved round by round in one
    container (B C1 C2 ... B C1 C2 ...), so all of them see the same
    machine state. Candidates are copied into the first one's workdir."""
    n = n or adaptive_runs(program_id)
    workdir = get_candidate_dir(candidate_ids[0])
    base_dir = get_candidate_dir(baseline_candidate(program_id))
    shutil.copy(pathlib.Path(base_dir, "prog"), pathlib.Path(workdir, "base_prog"))
    names = ["base_prog", "prog"]
    for i, cid in enumerate(candidate_ids[1:], start=1):
        shutil.copy(pathlib.Path(get_candidate_dir(cid), "prog"), pathlib.Path(workdir, f"cand{i}"))
        names.append(f"cand{i}")
    has_reference = False
    if reference_id:
        try:
            shutil.copy(pathlib.Path(get_candidate_dir(reference_id), "prog"), pathlib.Path(workdir, "ref_prog"))
            names.append("ref_prog")
            has_reference = True
        except (KeyError, OSError):
            pass  # evicted or gone: fall back to comparing point estimates
    input_name = _stage_input(workdir, program_id)
    timeout_s = load_meta(program_id).get("timeout_s", 20)

    samples = _run_harness(workdir, names, input_name, n, warmup, timeout_s)
    baseline = summarize(samples[0])
    reference = summarize(samples[-1]) if has_reference else None
    cand_samples = samples[1:-1] if has_reference else samples[1:]
    return [compare_results(baseline, summarize(s), reference) for s in cand_samples]


def compare_results(baseline: BenchResult, candidate: BenchResult,
                    reference: BenchResult | None = None) -> CompareResult:
    if not candidate.runtimes_ms or not baseline.runtimes_ms or candidate.failed_runs:
        return CompareResult(speedup=0.0, p_value=1.0, accepted_by_rule=False,
                             baseline=baseline, candidate=candidate)

    # hrtime resolves to nanoseconds, so a zero median would mean a broken
    # measurement rather than a fast program; guard the division anyway.
    speedup = baseline.median_ms / max(candidate.median_ms, 1e-3)
    cpu_speedup = baseline.cpu_median_ms / max(candidate.cpu_median_ms, 1e-3) if candidate.cpu_median_ms else 0.0
    try:
        _, p_value = mannwhitneyu(baseline.runtimes_ms, candidate.runtimes_ms, alternative="greater")
    except ValueError:
        p_value = 1.0

    vs_best_speedup = vs_best_p = None
    if reference is not None and reference.runtimes_ms and not reference.failed_runs:
        vs_best_speedup = reference.median_ms / max(candidate.median_ms, 1e-3)
        try:
            _, vs_best_p = mannwhitneyu(reference.runtimes_ms, candidate.runtimes_ms, alternative="greater")
            vs_best_p = float(vs_best_p)
        except ValueError:
            vs_best_p = 1.0

    accepted = speedup >= MIN_SPEEDUP and p_value < P_VALUE_THRESHOLD
    return CompareResult(
        speedup=speedup, p_value=float(p_value), accepted_by_rule=accepted,
        cpu_speedup=cpu_speedup, baseline=baseline, candidate=candidate,
        reference=reference if vs_best_p is not None else None,
        vs_best_speedup=vs_best_speedup, vs_best_p_value=vs_best_p,
        low_precision=candidate.median_ms < LOW_PRECISION_MS or candidate.cv > LOW_PRECISION_CV,
    )
