"""Timing stability test (Section 6.6).

Benchmarks each program's -O2 baseline `--runs` times in each of
`--sessions` separate sessions (separate containers, so caches, CPU
frequency and scheduler state are not shared) and reports the coefficient
of variation per program, within and across sessions. Also writes the
machine description the plan asks for (results/machine.json).

    python -m optiflow.experiments.stability --subset --runs 30 --sessions 3
"""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import statistics
import tempfile

from optiflow.tools import bench, registry
from optiflow.tools.sandbox import run_in_sandbox

OUT_PATH = pathlib.Path("results/stability.json")
MACHINE_PATH = pathlib.Path("results/machine.json")


def machine_info() -> dict:
    probe = run_in_sandbox(
        tempfile.mkdtemp(),
        "grep -m1 'model name' /proc/cpuinfo; nproc; grep MemTotal /proc/meminfo; uname -r; "
        "gcc --version | head -1; clang --version | head -1",
        timeout_s=30,
    )
    lines = [l.strip() for l in probe["stdout"].splitlines() if l.strip()]
    return {
        "cpu": lines[0].split(":", 1)[-1].strip() if lines else "",
        "cores_visible": lines[1] if len(lines) > 1 else "",
        "mem": lines[2].split(":", 1)[-1].strip() if len(lines) > 2 else "",
        "kernel": lines[3] if len(lines) > 3 else "",
        "gcc": lines[4] if len(lines) > 4 else "",
        "clang": lines[5] if len(lines) > 5 else "",
        "host_os": platform.platform(),
        "host_python": platform.python_version(),
    }


def measure(program_ids: list[str], runs: int, sessions: int) -> dict:
    results = {}
    for pid in program_ids:
        cand = bench.baseline_candidate(pid)
        session_stats = []
        for _ in range(sessions):
            r = bench.summarize(
                bench._run_harness(bench.get_candidate_dir(cand), ["prog"],
                                   bench._stage_input(bench.get_candidate_dir(cand), pid),
                                   runs, bench.DEFAULT_WARMUP,
                                   registry.load_meta(pid).get("timeout_s", 20))[0]
            )
            session_stats.append({"median_ms": r.median_ms, "cv": r.cv, "cpu_median_ms": r.cpu_median_ms,
                                  "cpu_cv": r.cpu_cv})
        medians = [s["median_ms"] for s in session_stats]
        across = (statistics.stdev(medians) / statistics.mean(medians)) if len(medians) > 1 and statistics.mean(medians) else 0.0
        results[pid] = {
            "median_ms": statistics.median(medians),
            "cv_within_max": max(s["cv"] for s in session_stats),
            "cv_across_sessions": across,
            "cpu_cv_within_max": max(s["cpu_cv"] for s in session_stats),
            "sessions": session_stats,
        }
        print(f"{pid:24s} median={results[pid]['median_ms']:9.1f} ms  "
              f"cv_within={results[pid]['cv_within_max']:.3f}  cpu_cv={results[pid]['cpu_cv_within_max']:.3f}  "
              f"cv_across={across:.3f}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subset", action="store_true", help="only the 10-program subset")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--programs", nargs="*", help="explicit program ids")
    args = parser.parse_args()

    ids = args.programs or registry.list_programs(subset10_only=args.subset)
    machine = machine_info()
    MACHINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MACHINE_PATH.write_text(json.dumps(machine, indent=2))

    results = measure(ids, args.runs, args.sessions)
    payload = {"runs": args.runs, "sessions": args.sessions, "machine": machine, "programs": results}
    # Merge with any earlier results so partial reruns don't erase the table.
    if OUT_PATH.exists():
        previous = json.loads(OUT_PATH.read_text())
        merged = previous.get("programs", {})
        merged.update(results)
        payload["programs"] = merged
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    stable = sum(1 for r in results.values() if r["cv_within_max"] < 0.03)
    print(f"\n{stable}/{len(results)} programs with within-session CV < 3%  ->  {OUT_PATH}")


if __name__ == "__main__":
    main()
