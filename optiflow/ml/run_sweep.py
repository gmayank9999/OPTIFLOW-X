"""Entrypoint for the sweep dataset build: `python -m optiflow.ml.run_sweep`.

Deliberately separate from build_dataset.py itself -- running that file
directly with -m would load it as __main__, a different module object
than optiflow.ml.build_dataset, and templates.py registers its variants
into the latter. Importing both normally here keeps it to one copy.

Resumable: per-program sweep results are cached in
results/ml_sweep_detail.json, so an interrupted sweep picks up where it
stopped. `--rebuild` re-measures everything; `--only` limits programs;
`--labels-only` just rebuilds the CSV (e.g. after new agent experience).
"""

import argparse
import json

import optiflow.ml.templates  # noqa: F401  (populates build_dataset.TEMPLATES)
from optiflow.ml.build_dataset import DETAIL_PATH, OUT_PATH, merge_experience, rows_from_sweep, sweep_program, write_csv
from optiflow.tools import registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--labels-only", action="store_true")
    args = parser.parse_args()

    details: dict[str, dict] = {}
    if DETAIL_PATH.exists() and not args.rebuild:
        details = {d["program_id"]: d for d in json.loads(DETAIL_PATH.read_text())}

    if not args.labels_only:
        for pid in args.only or registry.list_programs():
            if pid in details and not args.only:
                continue
            d = sweep_program(pid)
            details[pid] = d
            DETAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
            DETAIL_PATH.write_text(json.dumps(list(details.values()), indent=1))
            summary = ", ".join(
                f"{v['name']}={v.get('speedup', v['status'])}" + ("*" if v.get("positive") else "")
                for v in d["variants"]
            )
            print(f"{pid:24s} {summary}", flush=True)

    ordered = [details[p] for p in registry.list_programs() if p in details]
    rows = rows_from_sweep(ordered)
    filled = merge_experience(rows)
    write_csv(rows)
    print(f"wrote {len(rows)} rows to {OUT_PATH} ({filled} labels filled from agent experience)")


if __name__ == "__main__":
    main()
