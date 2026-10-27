import joblib

from optiflow.ml import predictor
from optiflow.ml.predictor import heuristic_scores, rank

MATMUL_FEATURES = {"max_loop_depth": 3.0, "n_loops": 3.0, "n_nested_loops": 2.0, "stride_mismatch": 1.0, "uses_float": 1.0}
RECURSIVE_FEATURES = {"max_loop_depth": 0.0, "n_loops": 0.0, "has_recursion": 1.0}
SORT_FEATURES = {"max_loop_depth": 2.0, "n_loops": 4.0, "n_array_accesses": 14.0, "uses_float": 0.0}


def test_heuristic_ranks_interchange_and_tiling_highly_for_stride_mismatch():
    s = heuristic_scores(MATMUL_FEATURES)
    top3 = sorted(s, key=s.get, reverse=True)[:3]
    assert "interchange" in top3 and "tiling" in top3


def test_heuristic_ranks_memoize_highest_for_recursion():
    s = heuristic_scores(RECURSIVE_FEATURES)
    assert max(s, key=s.get) == "memoize"


def test_heuristic_suggests_algorithmic_for_quadratic_integer_loops():
    s = heuristic_scores(SORT_FEATURES)
    assert max(s, key=s.get) == "algorithmic"


def test_rank_returns_requested_top_k_count():
    ranked = rank(MATMUL_FEATURES, top_k=5)
    assert len(ranked) == 5
    assert all(isinstance(name, str) and isinstance(score, float) for name, score in ranked)


def test_old_format_model_is_ignored(tmp_path, monkeypatch):
    """A v1 multi-output model trained on mislabeled data must not be used."""
    path = tmp_path / "model.joblib"
    joblib.dump({"not": "a v2 bundle"}, path)
    monkeypatch.setattr(predictor, "MODEL_PATH", path)
    predictor.reload()
    try:
        assert set(predictor.backends().values()) == {"heuristic"}
        assert rank(MATMUL_FEATURES, top_k=3) == [(n, round(s, 3)) for n, s in sorted(
            heuristic_scores(MATMUL_FEATURES).items(), key=lambda kv: kv[1], reverse=True)[:3]]
    finally:
        predictor.reload()
