"""Entrypoint for the sweep dataset build: `python -m optiflow.ml.run_sweep`.

Deliberately separate from build_dataset.py itself -- running that file
directly with -m would load it as __main__, a different module object
than optiflow.ml.build_dataset, and templates.py registers its variants
into the latter. Importing both normally here keeps it to one copy.
"""

import optiflow.ml.templates  # noqa: F401  (populates build_dataset.TEMPLATES)
from optiflow.ml.build_dataset import OUT_PATH, build, write_csv

if __name__ == "__main__":
    rows = build()
    write_csv(rows)
    print(f"wrote {len(rows)} rows to {OUT_PATH}")
