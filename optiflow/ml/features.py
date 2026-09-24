"""Feature vector shared by the sweep dataset builder, trainer and predictor.

Keeping the column order in one place means build_dataset.py, train_xgb.py
and predictor.py can never silently disagree on what column N means.
"""

from __future__ import annotations

FEATURE_COLUMNS = [
    "max_loop_depth",
    "n_loops",
    "n_nested_loops",
    "n_array_accesses",
    "stride_mismatch",
    "has_recursion",
    "n_mallocs_in_loop",
    "uses_float",
    "has_struct_array",
    "strlen_in_loop_cond",
    "loc",
]

STRATEGY_COLUMNS = [
    "flags",
    "interchange",
    "tiling",
    "vectorize",
    "unroll",
    "fusion",
    "fission",
    "soa",
    "hoist",
    "memoize",
]


def to_vector(features: dict[str, float]) -> list[float]:
    return [float(features.get(col, 0.0)) for col in FEATURE_COLUMNS]
