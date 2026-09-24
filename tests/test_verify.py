from optiflow.tools.verify import outputs_match


def test_exact_match():
    assert outputs_match("42\n", "42\n", "exact", 0.0)
    assert not outputs_match("42\n", "43\n", "exact", 0.0)


def test_float_tol_within_tolerance():
    assert outputs_match("3.140001", "3.140000", "float_tol", 1e-5)


def test_float_tol_outside_tolerance():
    assert not outputs_match("3.5", "3.140000", "float_tol", 1e-5)


def test_float_tol_token_count_mismatch():
    assert not outputs_match("1.0 2.0", "1.0", "float_tol", 1e-5)


def test_float_tol_non_numeric_tokens_compared_exactly():
    assert outputs_match("PASS 1.0", "PASS 1.0", "float_tol", 1e-5)
    assert not outputs_match("PASS 1.0", "FAIL 1.0", "float_tol", 1e-5)
