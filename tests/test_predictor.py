from optiflow.ml.predictor import rank

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


def test_matmul_ranks_interchange_and_tiling_highly():
    ranked = rank(MATMUL_FEATURES, top_k=3)
    names = [name for name, _ in ranked]
    assert "interchange" in names
    assert "tiling" in names


def test_recursive_program_ranks_memoize_highest():
    ranked = rank(RECURSIVE_FEATURES, top_k=1)
    assert ranked[0][0] == "memoize"


def test_returns_requested_top_k_count():
    ranked = rank(MATMUL_FEATURES, top_k=5)
    assert len(ranked) == 5
