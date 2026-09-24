"""Baseline dynamic profiling: timing plus hardware counters where available.

perf needs kernel permission inside the container, so it only runs on the
trusted baseline program, never on LLM-generated candidates. When perf
counters aren't available (WSL, restricted cloud VM), cachegrind stands in
for cache-miss rates.
"""

from __future__ import annotations

import pathlib
import re

from optiflow.core.schemas import Hotspot, ProfileReport
from optiflow.tools.compile import compile_and_register
from optiflow.tools.registry import _program_dir, load
from optiflow.tools.sandbox import run_in_sandbox

_PERF_EVENTS = (
    "cycles,instructions,cache-references,cache-misses,"
    "L1-dcache-loads,L1-dcache-load-misses,branches,branch-misses"
)


def profile(program_id: str, n: int = 5) -> ProfileReport:
    from optiflow.tools.bench import get_baseline

    baseline = get_baseline(program_id, n=n)
    program = load(program_id)
    meta = program["meta"]
    bench_input = _program_dir(program_id) / meta["bench_input"]

    build = compile_and_register(program["source"], meta["language"], "gcc", ["-O2", "-g"])
    workdir_dest = pathlib.Path(build.binary_path).parent / bench_input.name
    if not workdir_dest.exists():
        workdir_dest.write_bytes(bench_input.read_bytes())

    counters = _perf_stat(str(workdir_dest.parent), bench_input.name, meta.get("timeout_s", 20))

    hotspots = [
        Hotspot(function="main", start_line=1, end_line=1, time_pct=100.0, loop_depth=1)
    ]
    bottleneck_text = _describe_bottleneck(counters)

    return ProfileReport(
        baseline_runtime_ms=baseline.median_ms,
        runtime_std_ms=baseline.std_ms,
        peak_mem_kb=baseline.peak_mem_kb,
        ipc=counters.get("ipc"),
        l1_miss_rate=counters.get("l1_miss_rate"),
        llc_miss_rate=counters.get("llc_miss_rate"),
        branch_miss_rate=counters.get("branch_miss_rate"),
        hotspots=hotspots,
        bottleneck_text=bottleneck_text,
    )


def _perf_stat(workdir: str, input_name: str, timeout_s: int) -> dict:
    cmd = f"perf stat -x, -e {_PERF_EVENTS} ./prog < {input_name} > /dev/null"
    result = run_in_sandbox(workdir, cmd, timeout_s=timeout_s, privileged_perf=True)
    counters = _parse_perf_csv(result["stderr"])
    if counters:
        return counters
    return _cachegrind_fallback(workdir, input_name, timeout_s)


def _parse_perf_csv(stderr: str) -> dict:
    raw: dict[str, float] = {}
    for line in stderr.splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            value = float(parts[0])
        except ValueError:
            continue
        event = parts[2].strip()
        raw[event] = value

    if not raw.get("cycles") or not raw.get("instructions"):
        return {}

    out: dict[str, float] = {"ipc": raw["instructions"] / raw["cycles"]}
    if raw.get("L1-dcache-loads"):
        out["l1_miss_rate"] = raw.get("L1-dcache-load-misses", 0) / raw["L1-dcache-loads"]
    if raw.get("cache-references"):
        out["llc_miss_rate"] = raw.get("cache-misses", 0) / raw["cache-references"]
    if raw.get("branches"):
        out["branch_miss_rate"] = raw.get("branch-misses", 0) / raw["branches"]
    return out


def _cachegrind_fallback(workdir: str, input_name: str, timeout_s: int) -> dict:
    cmd = f"valgrind --tool=cachegrind --cache-sim=yes ./prog < {input_name} > /dev/null"
    result = run_in_sandbox(workdir, cmd, timeout_s=timeout_s * 30)
    text = result["stderr"]

    l1_miss_rate = _rate_from_summary(text, "D1  miss rate")
    llc_miss_rate = _rate_from_summary(text, "LLd miss rate")

    out: dict[str, float] = {}
    if l1_miss_rate is not None:
        out["l1_miss_rate"] = l1_miss_rate
    if llc_miss_rate is not None:
        out["llc_miss_rate"] = llc_miss_rate
    return out


def _rate_from_summary(text: str, label: str) -> float | None:
    m = re.search(rf"{re.escape(label)}:\s*([\d.]+)%", text)
    return float(m.group(1)) / 100.0 if m else None


def _describe_bottleneck(counters: dict) -> str:
    if not counters:
        return "no hardware counters available; treat as compute-bound"
    parts = []
    if "ipc" in counters:
        parts.append(f"IPC={counters['ipc']:.2f}")
    if "l1_miss_rate" in counters:
        parts.append(f"L1 miss rate={counters['l1_miss_rate']:.2%}")
    if "llc_miss_rate" in counters:
        parts.append(f"LLC miss rate={counters['llc_miss_rate']:.2%}")
    if "branch_miss_rate" in counters:
        parts.append(f"branch miss rate={counters['branch_miss_rate']:.2%}")
    return ", ".join(parts)
