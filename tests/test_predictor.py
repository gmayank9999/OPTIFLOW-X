from optiflow.ml.predictor import _heuristic_scores, rank

MATMUL_FEATURES = {
    "max_loop_depth": 3.0,
    "n_loops": 3.0,
    "n_nested_loops": 2.0,
    "stride_mismatch": 1.0,
    "has_recursion": 0.0,
    "has_struct_array": 0.0,
    "strlen_in_loop_cond": 0.0,
}

RECURSIVE_FEATURES = {
    "max_loop_depth": 0.0,
    "n_loops": 0.0,
    "has_recursion": 1.0,
    "stride_mismatch": 0.0,
}


def test_heuristic_ranks_interchange_and_tiling_highly_for_stride_mismatch():
    scores = _heuristic_scores(MATMUL_FEATURES)
    top3 = sorted(scores, key=scores.get, reverse=True)[:3]
    assert "interchange" in top3
    assert "tiling" in top3


def test_heuristic_ranks_memoize_highest_for_recursion():
    scores = _heuristic_scores(RECURSIVE_FEATURES)
    assert max(scores, key=scores.get) == "memoize"


def test_rank_returns_requested_top_k_count():
    # Exercises whatever backend is active (heuristic, or a trained model
    # if one happens to exist locally) -- only checks the API contract,
    # not which strategy comes out on top.
    ranked = rank(MATMUL_FEATURES, top_k=5)
    assert len(ranked) == 5
    assert all(isinstance(name, str) and isinstance(score, float) for name, score in ranked)
