"""Builds the labeled dataset the XGBoost predictor trains on.

Sources of labeled rows, no LLM involved in the first two:

1. Flag sweeps, applied to every program: -O3, -O3 -march=native,
   -O3 -funroll-loops, clang -O3. Purely mechanical.
2. Hand-written, single-strategy source variants (templates.py,
   templates_more.py) for programs where a strategy obviously applies.
   Writing them by hand is what keeps the label honest: the transform
   does what its name says, and it's verified against the reference
   outputs before it's labeled.
3. The agents' own judged attempts (results/experience.jsonl), used only
   to fill labels the sweep left untested (Section 11.3, step 3).

Labels are 1 (verified speedup >= 1.10, p < 0.05), 0 (tested, no such
speedup), or *missing* (never tested). Missing is not the same as 0: the
earlier version wrote untested strategies as negatives, which taught the
model that e.g. "tiling never helps" for 48 programs nobody tried tiling
on. The trainer only learns each strategy from rows where it was tested.

All variants of one program are benchmarked in a single interleaved
session together with the baseline (bench.compare_many), so they're
compared under identical machine conditions.
"""

from __future__ import annotations

import csv
import json
import pathlib

from optiflow.ml.features import FEATURE_COLUMNS, STRATEGY_COLUMNS, to_vector
from optiflow.tools import analyze as analyze_tool
from optiflow.tools import bench as bench_tool
from optiflow.tools import compile as compile_tool
from optiflow.tools import registry
from optiflow.tools import verify as verify_tool

OUT_PATH = pathlib.Path("results/ml_dataset.csv")
DETAIL_PATH = pathlib.Path("results/ml_sweep_detail.json")
EXPERIENCE_PATH = pathlib.Path("results/experience.jsonl")
LABEL_THRESHOLD = 1.10

FLAG_VARIANTS: list[tuple[str, str, list[str]]] = [
    ("gcc", "flags_O3", ["-O3"]),
    ("gcc", "flags_O3_native", ["-O3", "-march=native"]),
    ("gcc", "flags_O3_unroll", ["-O3", "-funroll-loops"]),
    ("clang", "flags_O3_clang", ["-O3"]),
]

# program_id -> {strategy_name: hand-written source}
TEMPLATES: dict[str, dict[str, str]] = {}


def register_template(program_id: str, strategy: str, source: str) -> None:
    TEMPLATES.setdefault(program_id, {})[strategy] = source.lstrip("\n")


def label_columns() -> list[str]:
    return [f"y_{s}" for s in STRATEGY_COLUMNS]


def sweep_program(pid: str, n: int | None = None) -> dict:
    """Compile + verify every variant of one program, then benchmark all
    the valid ones against the baseline in one interleaved session."""
    program = registry.load(pid)
    meta = program["meta"]
    lang = meta["language"]

    variants: list[dict] = []
    for compiler, name, flags in FLAG_VARIANTS:
        variants.append({"name": name, "strategy": "flags", "compiler": compiler,
                         "flags": flags, "source": program["source"]})
    for strategy, source in TEMPLATES.get(pid, {}).items():
        variants.append({"name": f"template_{strategy}", "strategy": strategy, "compiler": "gcc",
                         "flags": ["-O2"], "source": source})

    valid = []
    for v in variants:
        build = compile_tool.compile_and_register(v["source"], lang, v["compiler"], v["flags"])
        if not build.ok:
            v["status"] = "compile_error"
            v["detail"] = build.stderr[-300:]
            continue
        tests = verify_tool.run_tests(build.candidate_id, pid, sanitize=v["strategy"] != "flags")
        if not tests.all_pass:
            v["status"] = "failed_tests"
            v["detail"] = str(tests.failed_cases)
            continue
        v["candidate_id"] = build.candidate_id
        valid.append(v)

    if valid:
        results = bench_tool.compare_many([v["candidate_id"] for v in valid], pid, n=n)
        for v, r in zip(valid, results):
            v["status"] = "measured"
            v["speedup"] = round(r.speedup, 4)
            v["cpu_speedup"] = round(r.cpu_speedup, 4)
            v["p_value"] = r.p_value
            v["positive"] = bool(r.speedup >= LABEL_THRESHOLD and r.p_value < 0.05)

    for v in variants:
        v.pop("source", None)
        v.pop("candidate_id", None)
    return {"program_id": pid, "variants": variants}


def rows_from_sweep(details: list[dict]) -> list[dict]:
    rows = []
    for d in details:
        pid = d["program_id"]
        program = registry.load(pid)
        features = analyze_tool.analyze(program["source"], program["meta"]["language"])["features"]
        row = {"program_id": pid, "category": program["meta"].get("category", ""),
               **dict(zip(FEATURE_COLUMNS, to_vector(features)))}
        for strategy in STRATEGY_COLUMNS:
            measured = [v for v in d["variants"] if v["strategy"] == strategy and v.get("status") == "measured"]
            if measured:
                row[f"y_{strategy}"] = int(any(v["positive"] for v in measured))
                row[f"s_{strategy}"] = max(v["speedup"] for v in measured)
                row[f"src_{strategy}"] = "sweep"
            else:
                row[f"y_{strategy}"] = ""
        rows.append(row)
    return rows


def merge_experience(rows: list[dict], path: pathlib.Path = EXPERIENCE_PATH) -> int:
    """Fill sweep-untested labels from single-strategy agent attempts:
    accepted -> 1, measured but not significant -> 0. Correctness
    failures say nothing about the strategy (only about that rewrite),
    so they're ignored. Returns how many labels were filled."""
    if not path.exists():
        return 0
    by_pid = {r["program_id"]: r for r in rows}
    evidence: dict[tuple[str, str], list[int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if len(rec.get("strategies", [])) != 1:
            continue
        if rec.get("accepted"):
            label = 1
        elif rec.get("reason") == "no_significant_gain":
            label = 0
        else:
            continue
        evidence.setdefault((rec["program_id"], rec["strategies"][0]), []).append(label)

    filled = 0
    for (pid, strategy), labels in evidence.items():
        row = by_pid.get(pid)
        if row is None or strategy not in STRATEGY_COLUMNS or row.get(f"y_{strategy}") != "":
            continue
        row[f"y_{strategy}"] = int(any(labels))
        row[f"src_{strategy}"] = "agent"
        filled += 1
    return filled


def write_csv(rows: list[dict], path: pathlib.Path = OUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = [f"{p}_{s}" for s in STRATEGY_COLUMNS for p in ("s", "src")]
    fieldnames = ["program_id", "category", *FEATURE_COLUMNS, *label_columns(), *extra]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(
        "Run `python -m optiflow.ml.run_sweep` instead. Executing this file "
        "directly with -m makes it load as __main__, which is a different "
        "module object than optiflow.ml.build_dataset -- templates.py "
        "registers into the latter, so TEMPLATES would look empty here."
    )
