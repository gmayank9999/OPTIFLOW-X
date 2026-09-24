"""Builds the labeled sweep dataset the XGBoost predictor trains on.

Two sources of labeled rows, no LLM involved in either:

1. Flag sweeps, applied to every program: -O3, -O3 -march=native,
   -O3 -funroll-loops, clang -O3. Purely mechanical, so this alone
   gives real coverage of the "flags" strategy across the whole suite.

2. Hand-written, templated source variants for the subset of programs
   where a single strategy obviously applies (Section 11.3) -- a
   blocked matmul for the stride-mismatch matrix programs, a memoized
   rewrite for the recursive ones, and so on. These are deliberately
   *not* auto-generated: writing them by hand is what keeps the label
   honest (the transform actually does what its name says).

Each variant is compiled, run against the program's own reference
outputs, and benchmarked against the -O2 baseline. label = 1 iff the
speedup is >= 1.10 with the same significance test the Critic uses.
"""

from __future__ import annotations

import csv
import pathlib

from optiflow.ml.features import FEATURE_COLUMNS, STRATEGY_COLUMNS, to_vector
from optiflow.tools import analyze as analyze_tool
from optiflow.tools import bench as bench_tool
from optiflow.tools import compile as compile_tool
from optiflow.tools import registry
from optiflow.tools import verify as verify_tool

OUT_PATH = pathlib.Path("results/ml_dataset.csv")
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
    TEMPLATES.setdefault(program_id, {})[strategy] = source


def _evaluate(program_id: str, lang: str, source: str, compiler: str, flags: list[str]) -> bool | None:
    """Returns True/False for a labeled outcome, or None if the candidate
    didn't even compile/pass tests (excluded from the dataset, not a 0)."""
    build = compile_tool.compile_and_register(source, lang, compiler, flags)
    if not build.ok:
        return None
    tests = verify_tool.run_tests(build.candidate_id, program_id)
    if not tests.all_pass:
        return None
    compare = bench_tool.compare(build.candidate_id, program_id, n=10)
    return compare.speedup >= LABEL_THRESHOLD and compare.p_value < 0.05


def build(program_ids: list[str] | None = None) -> list[dict]:
    ids = program_ids or registry.list_programs()
    rows: list[dict] = []

    for pid in ids:
        program = registry.load(pid)
        meta = program["meta"]
        lang = meta["language"]
        analysis = analyze_tool.analyze(program["source"], lang)
        features = analysis["features"]

        labels = {name: 0 for name in STRATEGY_COLUMNS}
        any_label = False

        for compiler, _, flags in FLAG_VARIANTS:
            result = _evaluate(pid, lang, program["source"], compiler, flags)
            if result:
                labels["flags"] = 1
                any_label = True

        for strategy, source in TEMPLATES.get(pid, {}).items():
            result = _evaluate(pid, lang, source, "gcc", ["-O2"])
            if result:
                labels[strategy] = 1
                any_label = True
            elif result is False:
                any_label = True  # a confirmed negative is still a real row

        row = {"program_id": pid, **dict(zip(FEATURE_COLUMNS, to_vector(features))), **labels}
        rows.append(row)
        print(f"{pid:24s} " + " ".join(name for name, v in labels.items() if v))

    return rows


def write_csv(rows: list[dict], path: pathlib.Path = OUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["program_id", *FEATURE_COLUMNS, *STRATEGY_COLUMNS]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(
        "Run `python -m optiflow.ml.run_sweep` instead. Executing this file "
        "directly with -m makes it load as __main__, which is a different "
        "module object than optiflow.ml.build_dataset -- templates.py "
        "registers into the latter, so TEMPLATES would look empty here."
    )
