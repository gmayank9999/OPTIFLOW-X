from optiflow.tools.compile import compile_and_register
from optiflow.tools.registry import load
from optiflow.tools.verify import outputs_match, run_tests


def test_exact_match():
    assert outputs_match("42\n", "42", "exact", 0.0)
    assert not outputs_match("43", "42", "exact", 0.0)


def test_float_tol_within_tolerance():
    assert outputs_match("1.0000001", "1.0", "float_tol", 1e-6)


def test_float_tol_outside_tolerance():
    assert not outputs_match("1.01", "1.0", "float_tol", 1e-6)


def test_float_tol_token_count_mismatch():
    assert not outputs_match("1.0 2.0", "1.0", "float_tol", 1e-6)


def test_float_tol_non_numeric_tokens_compared_exactly():
    assert outputs_match("sum= 1.0", "sum= 1.0", "float_tol", 1e-6)
    assert not outputs_match("total= 1.0", "sum= 1.0", "float_tol", 1e-6)


def test_crash_after_printing_the_right_answer_is_a_failure():
    """Exit status matters: right output followed by a crash must not pass."""
    src = load("fib_recursive")["source"].replace("return 0;\n}", "int *p = 0; *p = 1;\n    return 0;\n}")
    build = compile_and_register(src, "c", "gcc", ["-O0"])
    result = run_tests(build.candidate_id, "fib_recursive", sanitize=False)
    assert not result.all_pass
    assert all(d["status"].startswith("exit_") for d in result.details.values())


def test_sanitizer_catches_out_of_bounds_read_that_outputs_correctly():
    """The reference outputs alone miss this; ASan doesn't."""
    src = load("bubble_sort")["source"].replace(
        "long long checksum = 0;",
        "long long checksum = 0;\n    volatile int junk = a[n]; (void)junk;  /* one past the end */",
    )
    build = compile_and_register(src, "c", "gcc", ["-O2"])
    result = run_tests(build.candidate_id, "bubble_sort", sanitize=True)
    assert result.sanitizer_ok is False
    assert result.failed_cases == ["sanitizer"]
