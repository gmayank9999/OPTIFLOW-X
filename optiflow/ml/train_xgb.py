"""Trains the multi-label strategy classifier from the sweep dataset.

GroupKFold by program_id so a program never appears in both train and
test -- otherwise the model could "learn" a specific program's row
instead of generalizing from its features. Reports per-strategy
ROC-AUC and top-1/top-3 hit rate against a naive "always suggest
flags + interchange" baseline, per Section 11.3.
"""

from __future__ import annotations

import json
import pathlib

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.multioutput import MultiOutputClassifier
from xgboost import XGBClassifier

from optiflow.ml.features import FEATURE_COLUMNS, STRATEGY_COLUMNS

DATASET_PATH = pathlib.Path("results/ml_dataset.csv")
MODEL_PATH = pathlib.Path("optiflow/ml/models/xgb_strategy_model.joblib")
REPORT_PATH = pathlib.Path("results/xgb_report.json")
NAIVE_BASELINE = ["flags", "interchange"]


def load_dataset() -> pd.DataFrame:
    return pd.read_csv(DATASET_PATH)


def top_k_hit_rate(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    """Fraction of rows where at least one true-positive label is in the
    model's top-k predicted strategies. Rows with no positive label at
    all are skipped -- there's nothing for "hit" to mean there."""
    hits, total = 0, 0
    for true_row, score_row in zip(y_true, y_score):
        positive = np.where(true_row == 1)[0]
        if len(positive) == 0:
            continue
        total += 1
        top_k = np.argsort(score_row)[::-1][:k]
        if any(p in top_k for p in positive):
            hits += 1
    return hits / total if total else float("nan")


def naive_baseline_hit_rate(y_true: np.ndarray, k: int) -> float:
    naive_idx = [STRATEGY_COLUMNS.index(name) for name in NAIVE_BASELINE if name in STRATEGY_COLUMNS]
    hits, total = 0, 0
    for true_row in y_true:
        positive = np.where(true_row == 1)[0]
        if len(positive) == 0:
            continue
        total += 1
        if any(p in naive_idx[:k] for p in positive):
            hits += 1
    return hits / total if total else float("nan")


def train() -> dict:
    df = load_dataset()
    X = df[FEATURE_COLUMNS]
    Y = df[STRATEGY_COLUMNS]
    groups = df["program_id"]

    # Strategies with fewer than 2 positive examples can't be split across
    # folds meaningfully; XGBoost still trains but AUC is undefined for them.
    label_counts = Y.sum()

    all_true, all_score = [], []
    n_splits = min(5, groups.nunique())
    for train_idx, test_idx in GroupKFold(n_splits=n_splits).split(X, Y, groups):
        model = MultiOutputClassifier(
            XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.8, eval_metric="logloss")
        )
        model.fit(X.iloc[train_idx], Y.iloc[train_idx])
        proba = model.predict_proba(X.iloc[test_idx])
        # one [P(0), P(1)] array per label; stack into (n_samples, n_labels)
        scores = np.column_stack([p[:, 1] if p.shape[1] > 1 else np.zeros(len(p)) for p in proba])
        all_true.append(Y.iloc[test_idx].values)
        all_score.append(scores)

    y_true = np.vstack(all_true)
    y_score = np.vstack(all_score)

    per_strategy_auc = {}
    for i, name in enumerate(STRATEGY_COLUMNS):
        if label_counts[name] < 2 or y_true[:, i].sum() == 0:
            per_strategy_auc[name] = None
            continue
        try:
            per_strategy_auc[name] = float(roc_auc_score(y_true[:, i], y_score[:, i]))
        except ValueError:
            per_strategy_auc[name] = None

    report = {
        "n_rows": len(df),
        "n_programs": int(groups.nunique()),
        "label_counts": {k: int(v) for k, v in label_counts.items()},
        "per_strategy_auc": per_strategy_auc,
        "top1_hit_rate": top_k_hit_rate(y_true, y_score, k=1),
        "top3_hit_rate": top_k_hit_rate(y_true, y_score, k=3),
        "naive_baseline_top1_hit_rate": naive_baseline_hit_rate(y_true, k=1),
        "naive_baseline_top3_hit_rate": naive_baseline_hit_rate(y_true, k=3),
    }

    # Final model trained on everything, for the predictor to load.
    final_model = MultiOutputClassifier(
        XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.1, subsample=0.8, eval_metric="logloss")
    )
    final_model.fit(X, Y)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, MODEL_PATH)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    return report


if __name__ == "__main__":
    report = train()
    print(json.dumps(report, indent=2))
