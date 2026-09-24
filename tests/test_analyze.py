from optiflow.tools.analyze import analyze

MATMUL_SRC = """
int main(void) {
    int n = 4;
    double A[16], B[16], C[16];
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            for (int k = 0; k < n; k++)
                C[i*n+j] += A[i*n+k] * B[k*n+j];
    return 0;
}
"""

RECURSIVE_SRC = """
long long fib(int n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}
"""


def test_detects_nested_loops_and_depth():
    result = analyze(MATMUL_SRC, "c")
    assert result["features"]["max_loop_depth"] == 3.0
    assert result["features"]["n_loops"] == 3.0


def test_detects_stride_mismatch_on_matmul():
    result = analyze(MATMUL_SRC, "c")
    assert result["features"]["stride_mismatch"] == 1.0


def test_detects_recursion():
    result = analyze(RECURSIVE_SRC, "c")
    assert result["features"]["has_recursion"] == 1.0


def test_no_recursion_on_matmul():
    result = analyze(MATMUL_SRC, "c")
    assert result["features"]["has_recursion"] == 0.0
