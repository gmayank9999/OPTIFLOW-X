"""Hand-written, single-strategy variants for the subset of benchmark
programs where a strategy obviously applies (Section 11.3). Each one
changes exactly the transformation it's labeled with and nothing else,
so a positive label in the sweep dataset means what it says.

Importing this module populates build_dataset.TEMPLATES as a side
effect via register_template().
"""

from optiflow.ml.build_dataset import register_template

register_template("matmul_naive", "tiling", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double *A = malloc(sizeof(double) * n * n);
    double *B = malloc(sizeof(double) * n * n);
    double *C = calloc((size_t)n * n, sizeof(double));
    for (int i = 0; i < n * n; i++) { A[i] = (i % 97) * 0.01; B[i] = (i % 89) * 0.02; }
    int BS = 32;
    for (int ii = 0; ii < n; ii += BS)
        for (int kk = 0; kk < n; kk += BS)
            for (int jj = 0; jj < n; jj += BS) {
                int imax = (ii + BS < n) ? ii + BS : n;
                int kmax = (kk + BS < n) ? kk + BS : n;
                int jmax = (jj + BS < n) ? jj + BS : n;
                for (int i = ii; i < imax; i++)
                    for (int k = kk; k < kmax; k++) {
                        double r = A[i * n + k];
                        for (int j = jj; j < jmax; j++)
                            C[i * n + j] += r * B[k * n + j];
                    }
            }
    double s = 0; for (int i = 0; i < n * n; i++) s += C[i];
    printf("%.6f\\n", s);
    free(A); free(B); free(C); return 0;
}
""")

register_template("transpose", "tiling", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double *A = malloc(sizeof(double) * n * n);
    double *B = malloc(sizeof(double) * n * n);
    for (int i = 0; i < n * n; i++) A[i] = (i % 131) * 0.01;
    int BS = 32;
    for (int ii = 0; ii < n; ii += BS)
        for (int jj = 0; jj < n; jj += BS) {
            int imax = (ii + BS < n) ? ii + BS : n;
            int jmax = (jj + BS < n) ? jj + BS : n;
            for (int i = ii; i < imax; i++)
                for (int j = jj; j < jmax; j++)
                    B[j * n + i] = A[i * n + j];
        }
    double s = 0; for (int i = 0; i < n * n; i++) s += B[i] * (i % 7 + 1);
    printf("%.6f\\n", s);
    free(A); free(B); return 0;
}
""")

register_template("matvec", "interchange", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double *A = malloc(sizeof(double) * n * n);
    double *x = malloc(sizeof(double) * n);
    double *y = calloc((size_t)n, sizeof(double));
    for (int i = 0; i < n * n; i++) A[i] = (i % 71) * 0.01;
    for (int i = 0; i < n; i++) x[i] = (i % 13) * 0.1;
    for (int i = 0; i < n; i++) {
        double sum = 0;
        for (int j = 0; j < n; j++) sum += A[i * n + j] * x[j];
        y[i] = sum;
    }
    double s = 0; for (int i = 0; i < n; i++) s += y[i];
    printf("%.6f\\n", s);
    free(A); free(x); free(y); return 0;
}
""")

register_template("colmajor_sum", "interchange", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double *A = malloc(sizeof(double) * (size_t)n * n);
    for (int i = 0; i < n * n; i++) A[i] = (i % 113) * 0.01;
    double s = 0;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            s += A[i * n + j];
    printf("%.6f\\n", s);
    free(A); return 0;
}
""")

register_template("frobenius_colwise", "interchange", """
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double *A = malloc(sizeof(double) * (size_t)n * n);
    for (int i = 0; i < n * n; i++) A[i] = (i % 137) * 0.01;
    double sumsq = 0;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            sumsq += A[i * n + j] * A[i * n + j];
    printf("%.6f\\n", sqrt(sumsq));
    free(A); return 0;
}
""")

register_template("syrk", "tiling", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n, k; if (scanf("%d %d", &n, &k) != 2) return 1;
    double *A = malloc(sizeof(double) * (size_t)n * k);
    double *C = calloc((size_t)n * n, sizeof(double));
    for (int i = 0; i < n * k; i++) A[i] = (i % 31) * 0.03;
    int BS = 32;
    for (int ii = 0; ii < n; ii += BS)
        for (int jj = 0; jj < n; jj += BS) {
            int imax = (ii + BS < n) ? ii + BS : n;
            int jmax = (jj + BS < n) ? jj + BS : n;
            for (int i = ii; i < imax; i++)
                for (int j = jj; j < jmax; j++) {
                    double acc = C[i * n + j];
                    for (int p = 0; p < k; p++)
                        acc += A[i * k + p] * A[j * k + p];
                    C[i * n + j] = acc;
                }
        }
    double s = 0; for (int i = 0; i < n * n; i++) s += C[i];
    printf("%.6f\\n", s);
    free(A); free(C); return 0;
}
""")

register_template("jacobi2d", "tiling", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n, iters; if (scanf("%d %d", &n, &iters) != 2) return 1;
    double *u = calloc((size_t)n * n, sizeof(double));
    double *unew = calloc((size_t)n * n, sizeof(double));
    for (int i = 0; i < n; i++) { u[i * n] = 1.0; u[i * n + n - 1] = 1.0; }
    for (int j = 0; j < n; j++) { u[j] = 1.0; u[(n - 1) * n + j] = 1.0; }
    int BS = 32;
    for (int it = 0; it < iters; it++) {
        for (int ii = 1; ii < n - 1; ii += BS)
            for (int jj = 1; jj < n - 1; jj += BS) {
                int imax = (ii + BS < n - 1) ? ii + BS : n - 1;
                int jmax = (jj + BS < n - 1) ? jj + BS : n - 1;
                for (int i = ii; i < imax; i++)
                    for (int j = jj; j < jmax; j++)
                        unew[i * n + j] = 0.25 * (u[(i - 1) * n + j] + u[(i + 1) * n + j]
                                                 + u[i * n + j - 1] + u[i * n + j + 1]);
            }
        for (int i = 1; i < n - 1; i++)
            for (int j = 1; j < n - 1; j++)
                u[i * n + j] = unew[i * n + j];
    }
    double s = 0; for (int i = 0; i < n * n; i++) s += u[i];
    printf("%.6f\\n", s);
    free(u); free(unew); return 0;
}
""")

register_template("conv2d", "vectorize", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double * restrict img = malloc(sizeof(double) * (size_t)n * n);
    double * restrict out = calloc((size_t)n * n, sizeof(double));
    for (int i = 0; i < n * n; i++) img[i] = (i % 251) * 0.01;
    for (int i = 1; i < n - 1; i++)
        for (int j = 1; j < n - 1; j++) {
            double acc =
                img[(i - 1) * n + (j - 1)] * 1 + img[(i - 1) * n + (j + 1)] * -1 +
                img[i * n + (j - 1)] * 2       + img[i * n + (j + 1)] * -2 +
                img[(i + 1) * n + (j - 1)] * 1 + img[(i + 1) * n + (j + 1)] * -1;
            out[i * n + j] = acc;
        }
    double s = 0; for (int i = 0; i < n * n; i++) s += out[i];
    printf("%.6f\\n", s);
    free(img); free(out); return 0;
}
""")

register_template("fib_recursive", "memoize", """
#include <stdio.h>
#include <string.h>
static long long memo[512];
static char has[512];
static long long fib(int n) {
    if (n < 2) return n;
    if (has[n]) return memo[n];
    long long r = fib(n - 1) + fib(n - 2);
    memo[n] = r; has[n] = 1;
    return r;
}
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    memset(has, 0, sizeof(has));
    printf("%lld\\n", fib(n));
    return 0;
}
""")

register_template("rod_cutting_recursive", "memoize", """
#include <stdio.h>
#include <stdlib.h>
static int *price, *memo; static char *has;
static int cut_rod(int n) {
    if (n <= 0) return 0;
    if (has[n]) return memo[n];
    int best = -1;
    for (int i = 1; i <= n; i++) {
        int val = price[i] + cut_rod(n - i);
        if (val > best) best = val;
    }
    has[n] = 1; memo[n] = best;
    return best;
}
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    price = malloc(sizeof(int) * (n + 1));
    memo = malloc(sizeof(int) * (n + 1));
    has = calloc(n + 1, sizeof(char));
    price[0] = 0;
    for (int i = 1; i <= n; i++) price[i] = 2 + (i * 3) % 7;
    printf("%d\\n", cut_rod(n));
    free(price); free(memo); free(has); return 0;
}
""")

register_template("particles_aos", "soa", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n, steps; double dt;
    if (scanf("%d %d %lf", &n, &steps, &dt) != 3) return 1;
    double *x = malloc(sizeof(double) * n), *y = malloc(sizeof(double) * n), *z = malloc(sizeof(double) * n);
    double *vx = malloc(sizeof(double) * n), *vy = malloc(sizeof(double) * n), *vz = malloc(sizeof(double) * n);
    for (int i = 0; i < n; i++) {
        x[i] = (i % 97) * 0.1; y[i] = (i % 89) * 0.1; z[i] = (i % 83) * 0.1;
        vx[i] = (i % 13) * 0.01; vy[i] = (i % 17) * 0.01; vz[i] = (i % 19) * 0.01;
    }
    for (int s = 0; s < steps; s++)
        for (int i = 0; i < n; i++) {
            x[i] += vx[i] * dt; y[i] += vy[i] * dt; z[i] += vz[i] * dt;
        }
    double sum = 0;
    for (int i = 0; i < n; i++) sum += x[i] + y[i] + z[i];
    printf("%.6f\\n", sum);
    free(x); free(y); free(z); free(vx); free(vy); free(vz); return 0;
}
""")

register_template("struct_records_scan", "soa", """
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n, passes; if (scanf("%d %d", &n, &passes) != 2) return 1;
    double *salary = malloc(sizeof(double) * n);
    for (int i = 0; i < n; i++) salary[i] = 30000.0 + (i % 97) * 137.0;
    double total = 0;
    for (int p = 0; p < passes; p++)
        for (int i = 0; i < n; i++)
            total += salary[i];
    printf("%.6f\\n", total);
    free(salary); return 0;
}
""")

register_template("string_reversal_many", "hoist", """
#include <stdio.h>
#include <string.h>
#define MAXLEN 64
static void reverse_str(char *s, int n) {
    for (int i = 0; i < n / 2; i++) { char t = s[i]; s[i] = s[n - 1 - i]; s[n - 1 - i] = t; }
}
int main(void) {
    int n, reps; if (scanf("%d %d", &n, &reps) != 2) return 1;
    static char strs[20005][MAXLEN];
    static int lens[20005];
    for (int i = 0; i < n; i++) {
        if (scanf("%63s", strs[i]) != 1) return 1;
        lens[i] = (int)strlen(strs[i]);
    }
    long long checksum = 0;
    for (int r = 0; r < reps; r++)
        for (int i = 0; i < n; i++) {
            reverse_str(strs[i], lens[i]);
            checksum += (unsigned char)strs[i][0];
        }
    printf("%lld\\n", checksum);
    return 0;
}
""")

register_template("run_length_encoding", "hoist", """
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    static char s[2000005];
    if (scanf("%2000004s", s) != 1) return 1;
    int n = (int)strlen(s);
    char *out = malloc((size_t)n * 2 + 8);
    int outlen = 0;
    long long run_count_sum = 0;
    int i = 0;
    while (i < n) {
        int j = i;
        while (j < n && s[j] == s[i]) j++;
        int run_len = j - i;
        run_count_sum += run_len;
        char numbuf[16];
        int nl = sprintf(numbuf, "%d", run_len);
        for (int k = 0; k < nl; k++) out[outlen++] = numbuf[k];
        out[outlen++] = s[i];
        i = j;
    }
    out[outlen] = '\\0';
    printf("%d %lld\\n", outlen, run_count_sum);
    free(out); return 0;
}
""")

register_template("binary_search_resort", "hoist", """
#include <stdio.h>
#include <stdlib.h>
static void bubble_sort(int *a, int n) {
    for (int i = 0; i < n - 1; i++)
        for (int j = 0; j < n - 1 - i; j++)
            if (a[j] > a[j + 1]) { int t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; }
}
static int binary_search(int *a, int n, int target) {
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (a[mid] == target) return mid;
        if (a[mid] < target) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}
int main(void) {
    int n, q; if (scanf("%d %d", &n, &q) != 2) return 1;
    int *a = malloc(sizeof(int) * (size_t)n);
    for (int i = 0; i < n; i++) if (scanf("%d", &a[i]) != 1) return 1;
    bubble_sort(a, n);
    long long found = 0;
    for (int k = 0; k < q; k++) {
        int target; if (scanf("%d", &target) != 1) return 1;
        int idx = binary_search(a, n, target);
        if (idx >= 0) found += idx + 1;
    }
    printf("%lld\\n", found);
    free(a); return 0;
}
""")
