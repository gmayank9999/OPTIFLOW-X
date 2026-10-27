"""Strategy ranking prior for the Strategist.

A hybrid: for each strategy, use the trained XGBoost classifier *only if*
train_xgb.py found it beats the static heuristic on held-out programs;
otherwise use the heuristic. Until a model bundle exists, every strategy
uses the heuristic. Either way the output is a ranking prior for the
Strategist's prompt, never a decision.
"""

from __future__ import annotations

import pathlib

from optiflow.ml.features import FEATURE_COLUMNS, STRATEGY_COLUMNS, to_vector

MODEL_PATH = pathlib.Path("optiflow/ml/models/xgb_strategy_model.joblib")

_bundle = None
_bundle_checked = False


def _load_bundle():
    global _bundle, _bundle_checked
    if _bundle_checked:
        return _bundle
    _bundle_checked = True
    if MODEL_PATH.exists():
        import joblib

        loaded = joblib.load(MODEL_PATH)
        # Only the v2 per-strategy bundle is understood; an older
        # multi-output model (trained on mislabeled data) is ignored.
        if isinstance(loaded, dict) and loaded.get("version") == 2 and loaded.get("features") == FEATURE_COLUMNS:
            _bundle = loaded
    return _bundle


def reload() -> None:
    global _bundle, _bundle_checked
    _bundle, _bundle_checked = None, False


def backends() -> dict[str, str]:
    bundle = _load_bundle()
    return {s: (bundle["backend"].get(s, "heuristic") if bundle else "heuristic") for s in STRATEGY_COLUMNS}


def rank(features: dict[str, float], top_k: int = 5) -> list[tuple[str, float]]:
    scores = heuristic_scores(features)
    bundle = _load_bundle()
    if bundle:
        vector = [to_vector(features)]
        for strategy, model in bundle["models"].items():
            if bundle["backend"].get(strategy) == "model":
                scores[strategy] = float(model.predict_proba(vector)[0, 1])
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [(name, round(score, 3)) for name, score in ranked[:top_k]]


def heuristic_scores(features: dict[str, float]) -> dict[str, float]:
    """Static-feature rules of thumb from the technique cards. Not
    calibrated probabilities -- only the order matters."""
    f = lambda k: float(features.get(k, 0) or 0)  # noqa: E731
    scores = {name: 0.2 for name in STRATEGY_COLUMNS}
    scores["flags"] = 0.5
    scores["algorithmic"] = 0.25

    if f("stride_mismatch") >= 1:
        scores["interchange"] = 0.75
        scores["tiling"] = 0.65
    if f("max_loop_depth") >= 2:
        scores["vectorize"] = max(scores["vectorize"], 0.45 if f("uses_float") else 0.3)
        scores["unroll"] = 0.3
    if f("max_loop_depth") >= 3 and f("uses_float"):
        scores["tiling"] = max(scores["tiling"], 0.45)
    if f("has_recursion") >= 1:
        scores["memoize"] = 0.7
        scores["algorithmic"] = max(scores["algorithmic"], 0.5)
    if f("max_loop_depth") >= 2 and not f("uses_float") and not f("stride_mismatch"):
        # quadratic integer loops: sorts, scans, pairwise counts
        scores["algorithmic"] = max(scores["algorithmic"], 0.55)
    if f("has_struct_array") >= 1 or f("pointer_chasing") >= 1:
        scores["soa"] = 0.6
    if f("strlen_in_loop_cond") >= 1 or f("n_mallocs_in_loop") >= 1:
        scores["hoist"] = 0.6
    if f("n_loops") >= 3:
        scores["fusion"] = 0.3
        scores["fission"] = 0.25
    return scores
