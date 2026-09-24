#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, k;
    if (scanf("%d %d", &n, &k) != 2) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * k);
    double *C = calloc((size_t)n * n, sizeof(double));

    for (int i = 0; i < n * k; i++) A[i] = (i % 31) * 0.03;

    /* C += A * A^T, naive triple loop with a transposed access on the
       second operand: cache-hostile */
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            for (int p = 0; p < k; p++)
                C[i * n + j] += A[i * k + p] * A[j * k + p];

    double s = 0;
    for (int i = 0; i < n * n; i++) s += C[i];
    printf("%.6f\n", s);

    free(A); free(C);
    return 0;
}
