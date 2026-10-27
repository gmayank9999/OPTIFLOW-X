import numpy as np

from optiflow.ml.features import STRATEGY_COLUMNS
from optiflow.ml.train_xgb import naive_baseline_hit_rate, top_k_hit_rate

N = len(STRATEGY_COLUMNS)
nan = np.nan


def row(**labels):
    r = np.full(N, nan)
    for name, v in labels.items():
        r[STRATEGY_COLUMNS.index(name)] = v
    return r


def scores(**s):
    r = np.zeros(N)
    for name, v in s.items():
        r[STRATEGY_COLUMNS.index(name)] = v
    return r


def test_top1_hit_when_highest_score_matches_true_label():
    assert top_k_hit_rate(np.array([row(tiling=1)]), np.array([scores(tiling=0.9, flags=0.2)]), k=1) == 1.0


def test_top1_miss_when_highest_score_is_a_different_strategy():
    assert top_k_hit_rate(np.array([row(tiling=1)]), np.array([scores(flags=0.9, tiling=0.2)]), k=1) == 0.0


def test_top3_hit_when_true_label_in_top_three_scores():
    y = np.array([row(memoize=1)])
    s = np.array([scores(flags=0.9, interchange=0.8, memoize=0.7, tiling=0.1)])
    assert top_k_hit_rate(y, s, k=3) == 1.0


def test_rows_with_no_positive_label_are_excluded():
    y = np.array([row(tiling=0, flags=0), row(flags=1)])
    s = np.array([scores(tiling=0.9), scores(flags=0.9)])
    assert top_k_hit_rate(y, s, k=1) == 1.0


def test_untested_labels_never_count_as_hits():
    # memoize is untested (NaN) for this program; ranking it first is a miss, not a hit.
    y = np.array([row(flags=1)])
    s = np.array([scores(memoize=0.9, flags=0.1)])
    assert top_k_hit_rate(y, s, k=1) == 0.0


def test_naive_baseline_ranks_flags_interchange_tiling():
    y = np.array([row(flags=1), row(tiling=1), row(memoize=1)])
    assert naive_baseline_hit_rate(y, k=1) == 1 / 3
    assert naive_baseline_hit_rate(y, k=3) == 2 / 3
