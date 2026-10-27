"""Trains the per-strategy success classifiers and decides, honestly, where
they're worth using.

For each strategy:
  - train only on programs where that strategy was actually tested
    (missing labels are not negatives -- see build_dataset.py),
  - evaluate with leave-one-program-out CV (each row is one program, so
    this is GroupKFold with one group per fold: a program is never in
    both train and test),
  - compare the model's out-of-fold ROC-AUC with the static heuristic's
    AUC on the *same* rows,
  - use the model at prediction time only if it beats the heuristic and
    clears AUC 0.6; otherwise the predictor falls back to the heuristic
    for that strategy.

Strategies with too few labels (< 6 rows or < 2 of either class) never
get a model. The report says which backend each strategy ended up with
and why, plus top-1/top-3 hit rates for the hybrid ranking, the
heuristic alone, and a naive "flags, interchange, tiling" baseline.
"""

from __future__ import annotations

import json
import pathlib

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

from optiflow.ml.features import FEATURE_COLUMNS, STRATEGY_COLUMNS
from optiflow.ml.predictor import heuristic_scores

DATASET_PATH = pathlib.Path("results/ml_dataset.csv")
MODEL_PATH = pathlib.Path("optiflow/ml/models/xgb_strategy_model.joblib")
REPORT_PATH = pathlib.Path("results/xgb_report.json")
NAIVE_BASELINE = ["flags", "interchange", "tiling"]
MIN_ROWS, MIN_PER_CLASS, MIN_AUC = 6, 2, 0.6


def load_dataset() -> pd.DataFrame:
    return pd.read_csv(DATASET_PATH)


def _model() -> XGBClassifier:
    # Deliberately small: tens of rows per strategy at most.
    return XGBClassifier(n_estimators=60, max_depth=2, learning_rate=0.15, min_child_weight=1,
                         subsample=1.0, eval_metric="logloss", verbosity=0)


def top_k_hit_rate(y_true: np.ndarray, y_score: np.ndarray, k: int) -> float:
    """Fraction of rows where at least one true-positive label is in the
    top-k predicted strategies. NaN labels are untested and never count as
    hits; rows with no positive label at all are skipped."""
    hits, total = 0, 0
    for true_row, score_row in zip(y_true, y_score):
        positive = np.where(true_row == 1)[0]
        if len(positive) == 0:
            continue
        total += 1
        top_k = np.argsort(-np.asarray(score_row), kind="stable")[:k]
        if any(p in top_k for p in positive):
            hits += 1
    return hits / total if total else float("nan")


def naive_baseline_hit_rate(y_true: np.ndarray, k: int) -> float:
    naive_idx = [STRATEGY_COLUMNS.index(name) for name in NAIVE_BASELINE]
    scores = np.zeros((len(y_true), len(STRATEGY_COLUMNS)))
    for rank, idx in enumerate(naive_idx):
        scores[:, idx] = len(naive_idx) - rank
    return top_k_hit_rate(y_true, scores, k)


def _safe_auc(y: np.ndarray, s: np.ndarray) -> float | None:
    if len(set(y.tolist())) < 2:
        return None
    try:
        return float(roc_auc_score(y, s))
    except ValueError:
        return None


def train() -> dict:
    df = load_dataset()
    X_all = df[FEATURE_COLUMNS].astype(float).values
    heur = np.array([[heuristic_scores(dict(zip(FEATURE_COLUMNS, x)))[s] for s in STRATEGY_COLUMNS] for x in X_all])

    oof = heur.copy()  # out-of-fold hybrid scores; heuristic unless a model wins
    models, backend, per_strategy = {}, {}, {}
    for j, strategy in enumerate(STRATEGY_COLUMNS):
        y_col = pd.to_numeric(df[f"y_{strategy}"], errors="coerce")
        mask = y_col.notna().values
        y = y_col[mask].astype(int).values
        X = X_all[mask]
        n, pos = int(mask.sum()), int(y.sum()) if mask.any() else 0
        info = {"n_labeled": n, "n_positive": pos, "model_auc": None,
                "heuristic_auc": _safe_auc(y, heur[mask, j]) if n else None}

        if n < MIN_ROWS or pos < MIN_PER_CLASS or n - pos < MIN_PER_CLASS:
            backend[strategy] = "heuristic"
            info["backend"] = "heuristic"
            info["why"] = f"too few labels ({n} rows, {pos} positive)"
            per_strategy[strategy] = info
            continue

        preds = np.zeros(n)
        for i in range(n):
            train_idx = np.arange(n) != i
            if len(set(y[train_idx].tolist())) < 2:
                preds[i] = float(y[train_idx].mean())
                continue
            m = _model().fit(X[train_idx], y[train_idx])
            preds[i] = m.predict_proba(X[i:i + 1])[0, 1]
        info["model_auc"] = _safe_auc(y, preds)

        final = _model().fit(X, y)
        importances = dict(zip(FEATURE_COLUMNS, map(float, final.feature_importances_)))
        info["feature_importance"] = dict(sorted(importances.items(), key=lambda kv: -kv[1])[:6])

        model_auc, heur_auc = info["model_auc"] or 0.0, info["heuristic_auc"] or 0.0
        if model_auc >= MIN_AUC and model_auc > heur_auc:
            backend[strategy] = "model"
            models[strategy] = final
            oof[np.where(mask)[0], j] = preds
            info["why"] = f"model AUC {model_auc:.2f} > heuristic {heur_auc:.2f}"
        else:
            backend[strategy] = "heuristic"
            info["why"] = f"model AUC {model_auc:.2f} did not beat heuristic {heur_auc:.2f} / floor {MIN_AUC}"
        info["backend"] = backend[strategy]
        per_strategy[strategy] = info

    y_true = np.array([[pd.to_numeric(r, errors="coerce") for r in df[f"y_{s}"]] for s in STRATEGY_COLUMNS]).T
    report = {
        "n_programs": int(len(df)),
        "n_labels": int(np.sum(~np.isnan(y_true))),
        "n_positive_labels": int(np.nansum(y_true)),
        "label_sources": {
            "sweep": int(sum((df.get(f"src_{s}") == "sweep").sum() for s in STRATEGY_COLUMNS if f"src_{s}" in df)),
            "agent": int(sum((df.get(f"src_{s}") == "agent").sum() for s in STRATEGY_COLUMNS if f"src_{s}" in df)),
        },
        "per_strategy": per_strategy,
        "backend": backend,
        "ranking": {
            "programs_with_a_positive": int(np.sum(np.nansum(y_true, axis=1) > 0)),
            "hybrid_top1": top_k_hit_rate(y_true, oof, 1),
            "hybrid_top3": top_k_hit_rate(y_true, oof, 3),
            "heuristic_top1": top_k_hit_rate(y_true, heur, 1),
            "heuristic_top3": top_k_hit_rate(y_true, heur, 3),
            "naive_top1": naive_baseline_hit_rate(y_true, 1),
            "naive_top3": naive_baseline_hit_rate(y_true, 3),
        },
        "notes": (
            "Out-of-fold (leave-one-program-out) scores. The hybrid ranking uses a "
            "strategy's model only where it beat the heuristic on held-out programs."
        ),
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"version": 2, "features": FEATURE_COLUMNS, "backend": backend, "models": models}, MODEL_PATH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
