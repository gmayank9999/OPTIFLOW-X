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

INTERCHANGED_SRC = """
int main(void) {
    int n = 4;
    double A[16], B[16], C[16];
    for (int i = 0; i < n; i++)
        for (int k = 0; k < n; k++)
            for (int j = 0; j < n; j++)
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

HELPER_SRC = """
static int sq(int x) { return x * x; }
int main(void) {
    int s = 0;
    for (int i = 0; i < 10; i++) { s += sq(i); }
    for (int i = 0; i < 10; i++) { if (s > 3) { s--; } }
    return s;
}
"""

AOS_SRC = """
typedef struct { double x, vx, mass; } P;
int main(void) {
    P p[64];
    for (int s = 0; s < 10; s++)
        for (int i = 0; i < 64; i++) p[i].x += p[i].vx;
    return 0;
}
"""

ALLOC_STRLEN_SRC = """
#include <stdlib.h>
#include <string.h>
int main(void) {
    char *s = malloc(100);
    for (int i = 0; i < (int)strlen(s); i++) {
        char *tmp = malloc(16);
        free(tmp);
    }
    return 0;
}
"""


def test_detects_nested_loops_and_depth():
    result = analyze(MATMUL_SRC, "c")
    assert result["features"]["max_loop_depth"] == 3.0
    assert result["features"]["n_loops"] == 3.0


def test_detects_stride_mismatch_on_matmul():
    assert analyze(MATMUL_SRC, "c")["features"]["stride_mismatch"] == 1.0


def test_unbraced_nesting_marks_only_the_inner_loop_innermost():
    loops = analyze(MATMUL_SRC, "c")["loops"]
    assert [l["innermost"] for l in loops] == [False, False, True]


def test_interchanged_matmul_has_no_stride_mismatch():
    assert analyze(INTERCHANGED_SRC, "c")["features"]["stride_mismatch"] == 0.0


def test_detects_recursion():
    assert analyze(RECURSIVE_SRC, "c")["features"]["has_recursion"] == 1.0


def test_no_recursion_on_matmul():
    assert analyze(MATMUL_SRC, "c")["features"]["has_recursion"] == 0.0


def test_helper_call_and_braced_blocks_are_not_recursion():
    # The old regex flagged any file with two `for (...) {` blocks.
    assert analyze(HELPER_SRC, "c")["features"]["has_recursion"] == 0.0


def test_typedef_struct_array_is_detected():
    assert analyze(AOS_SRC, "c")["features"]["has_struct_array"] == 1.0


def test_mallocs_counted_only_inside_loops_and_strlen_only_in_conditions():
    f = analyze(ALLOC_STRLEN_SRC, "c")["features"]
    assert f["n_mallocs_in_loop"] == 1.0
    assert f["strlen_in_loop_cond"] == 1.0
