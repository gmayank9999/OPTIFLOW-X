import numpy as np

from optiflow.ml.features import STRATEGY_COLUMNS
from optiflow.ml.train_xgb import naive_baseline_hit_rate, top_k_hit_rate


def _one_hot(name: str) -> np.ndarray:
    row = np.zeros(len(STRATEGY_COLUMNS))
    row[STRATEGY_COLUMNS.index(name)] = 1
    return row


def test_top1_hit_when_highest_score_matches_true_label():
    y_true = np.array([_one_hot("tiling")])
    y_score = np.zeros((1, len(STRATEGY_COLUMNS)))
    y_score[0, STRATEGY_COLUMNS.index("tiling")] = 0.9
    assert top_k_hit_rate(y_true, y_score, k=1) == 1.0


def test_top1_miss_when_highest_score_is_a_different_strategy():
    y_true = np.array([_one_hot("tiling")])
    y_score = np.zeros((1, len(STRATEGY_COLUMNS)))
    y_score[0, STRATEGY_COLUMNS.index("flags")] = 0.9
    assert top_k_hit_rate(y_true, y_score, k=1) == 0.0


def test_top3_hit_when_true_label_in_top_three_scores():
    y_true = np.array([_one_hot("memoize")])
    y_score = np.zeros((1, len(STRATEGY_COLUMNS)))
    y_score[0, STRATEGY_COLUMNS.index("flags")] = 0.9
    y_score[0, STRATEGY_COLUMNS.index("interchange")] = 0.8
    y_score[0, STRATEGY_COLUMNS.index("memoize")] = 0.7
    assert top_k_hit_rate(y_true, y_score, k=3) == 1.0
    assert top_k_hit_rate(y_true, y_score, k=1) == 0.0


def test_rows_with_no_positive_label_are_excluded():
    y_true = np.zeros((1, len(STRATEGY_COLUMNS)))
    y_score = np.random.rand(1, len(STRATEGY_COLUMNS))
    import math
    assert math.isnan(top_k_hit_rate(y_true, y_score, k=1))


def test_naive_baseline_hits_only_flags_and_interchange():
    y_true = np.array([_one_hot("flags"), _one_hot("tiling")])
    rate = naive_baseline_hit_rate(y_true, k=2)
    assert rate == 0.5
