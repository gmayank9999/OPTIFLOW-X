"""Baseline dynamic profiling: timing, hardware counters, and loop hotspots.

perf needs CAP_PERFMON inside the container, so it only ever runs on the
trusted baseline program, never on LLM-generated candidates.

- Counters: `perf stat` (cycles, instructions, L1/LLC, branches). The
  sandbox image exposes the versioned perf binary as `perf-raw` because the
  distro wrapper refuses to run on WSL2/cloud kernels. When counters are
  unavailable, cachegrind supplies cache miss rates instead.
- Hotspots: `perf record` samples are attributed to source lines, then
  rolled up onto the loops tree-sitter found, so the Strategist is told
  *which loop* holds the time. Falls back to gprof's function-level flat
  profile when sampling isn't possible.

Profiles are deterministic for a given source, so they're cached on disk
(results/profiles/) and reused by every run and architecture -- that keeps
comparisons fair and saves the cachegrind/perf cost on repeat runs.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from collections import defaultdict

from optiflow.core.schemas import Hotspot, ProfileReport
from optiflow.tools import analyze as analyze_tool
from optiflow.tools.compile import compile_and_register
from optiflow.tools.registry import _program_dir, load
from optiflow.tools.sandbox import run_in_sandbox

CACHE_DIR = pathlib.Path("results/profiles")

_PERF_EVENTS = (
    "cycles,instructions,cache-references,cache-misses,"
    "L1-dcache-loads,L1-dcache-load-misses,branches,branch-misses"
)
_STAT_MARK = "===PERF-STAT==="
_SRCLINE_RE = re.compile(r"^\s*([\d.]+)%\s+\S*?main\.c(?:pp)?:(\d+)")


def profile(program_id: str, n: int = 5, use_cache: bool = True) -> ProfileReport:
    program = load(program_id)
    source, meta = program["source"], program["meta"]
    cache_path = CACHE_DIR / f"{program_id}.json"
    digest = hashlib.sha256(source.encode()).hexdigest()[:16]

    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text())
        if cached.get("source_sha") == digest:
            return _with_current_timing(program_id, ProfileReport(**cached["report"]))

    from optiflow.tools.bench import get_baseline

    baseline = get_baseline(program_id, n=n)
    analysis = analyze_tool.analyze(source, meta["language"])
    bench_input = _program_dir(program_id) / meta["bench_input"]
    timeout_s = meta.get("timeout_s", 20)

    build = compile_and_register(source, meta["language"], "gcc", ["-O2", "-g"])
    workdir = str(pathlib.Path(build.binary_path).parent)
    (pathlib.Path(workdir) / bench_input.name).write_bytes(bench_input.read_bytes())

    counters, line_pct = _perf_profile(workdir, bench_input.name, timeout_s)
    counters_source = "perf" if counters else "none"
    if not counters:
        small_input = _program_dir(program_id) / _smaller_input(meta)
        (pathlib.Path(workdir) / small_input.name).write_bytes(small_input.read_bytes())
        counters = _cachegrind(workdir, small_input.name, timeout_s)
        counters_source = "cachegrind" if counters else "none"

    if line_pct:
        hotspots = _loop_hotspots(line_pct, analysis)
    else:
        hotspots = _gprof_hotspots(source, meta["language"], bench_input, timeout_s, analysis)

    report = ProfileReport(
        baseline_runtime_ms=baseline.median_ms,
        runtime_std_ms=baseline.std_ms,
        peak_mem_kb=baseline.peak_mem_kb,
        ipc=counters.get("ipc"),
        l1_miss_rate=counters.get("l1_miss_rate"),
        llc_miss_rate=counters.get("llc_miss_rate"),
        branch_miss_rate=counters.get("branch_miss_rate"),
        hotspots=hotspots,
        counters_source=counters_source,
        bottleneck_text=describe_bottleneck(counters, hotspots),
    )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"source_sha": digest, "report": report.model_dump()}, indent=2))
    return report


def _with_current_timing(program_id: str, report: ProfileReport) -> ProfileReport:
    """Counter ratios and hotspot shares are properties of the program and
    safe to cache; absolute wall time is a property of the machine *right
    now*. Prefer the stability table's median over a cached timing."""
    try:
        stab = json.loads(pathlib.Path("results/stability.json").read_text())["programs"][program_id]
        sessions = stab.get("sessions") or []
        std = max((s["cv"] * s["median_ms"] for s in sessions), default=report.runtime_std_ms)
        return report.model_copy(update={"baseline_runtime_ms": stab["median_ms"], "runtime_std_ms": std})
    except (OSError, KeyError, ValueError):
        return report


def _smaller_input(meta: dict) -> str:
    others = [i for i in meta["inputs"] if i != meta["bench_input"]]
    return others[-1] if others else meta["bench_input"]


# --- perf --------------------------------------------------------------------

def _perf_profile(workdir: str, input_name: str, timeout_s: int) -> tuple[dict, dict[int, float]]:
    cmd = (
        f"cp prog /tmp/prog; "  # exec from tmpfs: the work dir may be noexec
        f"perf-raw stat -x, -e {_PERF_EVENTS} -o /tmp/stat.csv /tmp/prog < {input_name} > /dev/null; "
        f"perf-raw record -q -F 997 -o /tmp/perf.data /tmp/prog < {input_name} > /dev/null 2>&1; "
        f"perf-raw report -i /tmp/perf.data --stdio --no-children --sort srcline -q 2>/dev/null | head -400; "
        f"echo {_STAT_MARK}; cat /tmp/stat.csv"
    )
    result = run_in_sandbox(workdir, cmd, timeout_s=timeout_s * 4 + 30, privileged_perf=True)
    report_text, _, stat_text = result["stdout"].partition(_STAT_MARK)
    return parse_perf_csv(stat_text), parse_srclines(report_text)


def parse_perf_csv(text: str) -> dict:
    raw: dict[str, float] = {}
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            value = float(parts[0])
        except ValueError:
            continue  # "<not supported>" / "<not counted>"
        # perf appends a privilege modifier when it can only count user
        # space (e.g. "cycles:u"); strip it so names are stable.
        event = parts[2].strip().split(":")[0]
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


def parse_srclines(text: str) -> dict[int, float]:
    """`perf report --sort srcline` -> {source line: % of samples}."""
    pct: dict[int, float] = defaultdict(float)
    for line in text.splitlines():
        m = _SRCLINE_RE.match(line)
        if m:
            pct[int(m.group(2))] += float(m.group(1))
    return dict(pct)


def _loop_hotspots(line_pct: dict[int, float], analysis: dict, top: int = 3) -> list[Hotspot]:
    """Roll per-line samples up onto loops, then keep the *tightest* loop
    that still holds most of the time: a loop is reported only if none of
    its inner loops carries >= 85% of its share."""
    loops = analysis["loops"]
    scored = []
    for loop in loops:
        share = sum(p for line, p in line_pct.items() if loop["line"] <= line <= loop["end_line"])
        scored.append((loop, share))

    hotspots = []
    for loop, share in scored:
        if share < 5.0:
            continue
        inner = [s for l, s in scored
                 if l is not loop and loop["line"] <= l["line"] and l["end_line"] <= loop["end_line"]
                 and l["depth"] > loop["depth"]]
        if any(s >= 0.85 * share for s in inner):
            continue
        hotspots.append(Hotspot(
            function=loop["function"] or "?", start_line=loop["line"], end_line=loop["end_line"],
            time_pct=round(share, 1), loop_depth=loop["depth"],
        ))

    if not hotspots and line_pct:
        # Time sits outside any loop (e.g. pure recursion): report by function.
        for fn in analysis.get("function_spans", []):
            share = sum(p for line, p in line_pct.items() if fn["start_line"] <= line <= fn["end_line"])
            if share >= 5.0:
                hotspots.append(Hotspot(function=fn["name"], start_line=fn["start_line"],
                                        end_line=fn["end_line"], time_pct=round(share, 1), loop_depth=0))
    hotspots.sort(key=lambda h: h.time_pct, reverse=True)
    return hotspots[:top]


# --- fallbacks ---------------------------------------------------------------

def _cachegrind(workdir: str, input_name: str, timeout_s: int) -> dict:
    cmd = (f"cp prog /tmp/prog && valgrind --tool=cachegrind --cache-sim=yes --cachegrind-out-file=/tmp/cg.out "
           f"/tmp/prog < {input_name} > /dev/null")
    result = run_in_sandbox(workdir, cmd, timeout_s=timeout_s * 30)
    text = result["stderr"]
    out: dict[str, float] = {}
    l1 = _rate_from_summary(text, "D1  miss rate")
    llc = _rate_from_summary(text, "LLd miss rate")
    if l1 is not None:
        out["l1_miss_rate"] = l1
    if llc is not None:
        out["llc_miss_rate"] = llc
    return out


def _rate_from_summary(text: str, label: str) -> float | None:
    m = re.search(rf"{re.escape(label)}:\s*([\d.]+)%", text)
    return float(m.group(1)) / 100.0 if m else None


def _gprof_hotspots(source: str, lang: str, bench_input: pathlib.Path, timeout_s: int,
                    analysis: dict) -> list[Hotspot]:
    build = compile_and_register(source, lang, "gcc", ["-O2", "-g"], )
    if not build.ok:
        return []
    workdir = pathlib.Path(build.binary_path).parent
    (workdir / bench_input.name).write_bytes(bench_input.read_bytes())
    fname = "main.c" if lang == "c" else "main.cpp"
    cc = "gcc" if lang == "c" else "g++"
    cmd = (f"{cc} -O2 -g -pg {fname} -o /tmp/prog_pg -lm && cd /tmp && ./prog_pg < /work/{bench_input.name} "
           f"> /dev/null && gprof -b -p prog_pg gmon.out")
    result = run_in_sandbox(str(workdir), cmd, timeout_s=timeout_s * 3 + 60)

    spans = {f["name"]: f for f in analysis.get("function_spans", [])}
    max_depth = {name: max((l["depth"] for l in analysis["loops"] if l["function"] == name), default=0)
                 for name in spans}
    hotspots = []
    for line in result["stdout"].splitlines():
        parts = line.split()
        if len(parts) >= 7 and re.match(r"^[\d.]+$", parts[0]) and parts[-1] in spans:
            span = spans[parts[-1]]
            hotspots.append(Hotspot(function=parts[-1], start_line=span["start_line"],
                                    end_line=span["end_line"], time_pct=float(parts[0]),
                                    loop_depth=max_depth.get(parts[-1], 0)))
    hotspots.sort(key=lambda h: h.time_pct, reverse=True)
    return hotspots[:3]


def describe_bottleneck(counters: dict, hotspots: list[Hotspot]) -> str:
    parts = []
    if hotspots:
        h = hotspots[0]
        parts.append(f"{h.time_pct:.0f}% of samples in {h.function}() lines {h.start_line}-{h.end_line}"
                     f" (loop depth {h.loop_depth})")
    if "ipc" in counters:
        parts.append(f"IPC={counters['ipc']:.2f}")
    if "l1_miss_rate" in counters:
        parts.append(f"L1 miss rate={counters['l1_miss_rate']:.2%}")
    if "llc_miss_rate" in counters:
        parts.append(f"LLC miss rate={counters['llc_miss_rate']:.2%}")
    if "branch_miss_rate" in counters:
        parts.append(f"branch miss rate={counters['branch_miss_rate']:.2%}")
    return ", ".join(parts) if parts else "no hardware counters available; treat as compute-bound"
