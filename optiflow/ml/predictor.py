"""Strategy ranking prior for the Strategist.

Once train_xgb.py has produced a model from the sweep dataset
(Section 11.3), this loads it and ranks strategies by predicted success
probability. Until that model exists, it falls back to a static-feature
heuristic so the Strategist still has a prior to combine with RAG and its
own reasoning -- this is what the "no-XGB" ablation effectively runs
permanently.
"""

from __future__ import annotations

import pathlib

from optiflow.ml.features import STRATEGY_COLUMNS, to_vector

MODEL_PATH = pathlib.Path("optiflow/ml/models/xgb_strategy_model.joblib")

_model = None
_model_checked = False


def _load_model():
    global _model, _model_checked
    if _model_checked:
        return _model
    _model_checked = True
    if MODEL_PATH.exists():
        import joblib

        _model = joblib.load(MODEL_PATH)
    return _model


def rank(features: dict[str, float], top_k: int = 5) -> list[tuple[str, float]]:
    model = _load_model()
    if model is not None:
        scores = _predict_with_model(model, features)
    else:
        scores = _heuristic_scores(features)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:top_k]


def _predict_with_model(model, features: dict[str, float]) -> dict[str, float]:
    vector = [to_vector(features)]
    probs = model.predict_proba(vector)
    scores = {}
    for name, estimator_probs in zip(STRATEGY_COLUMNS, probs):
        # MultiOutputClassifier: one [P(0), P(1)] row per label per sample.
        scores[name] = float(estimator_probs[0][1])
    return scores


def _heuristic_scores(features: dict[str, float]) -> dict[str, float]:
    scores = {name: 0.3 for name in STRATEGY_COLUMNS}
    scores["flags"] = 0.6

    if features.get("stride_mismatch", 0) >= 1:
        scores["interchange"] = 0.75
        scores["tiling"] = 0.65
    if features.get("max_loop_depth", 0) >= 2:
        scores["vectorize"] = 0.55
        scores["unroll"] = 0.4
    if features.get("has_recursion", 0) >= 1:
        scores["memoize"] = 0.85
    if features.get("has_struct_array", 0) >= 1:
        scores["soa"] = 0.6
    if features.get("strlen_in_loop_cond", 0) >= 1:
        scores["hoist"] = 0.6
    if features.get("n_loops", 0) >= 2:
        scores["fusion"] = 0.35
        scores["fission"] = 0.3

    return scores
