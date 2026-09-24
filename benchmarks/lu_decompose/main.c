#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * n);
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            A[i * n + j] = (i == j) ? (n * 2.0) : ((i + j) % 7 + 1) * 0.1;

    /* naive LU decomposition without pivoting (matrix is diagonally
       dominant by construction, so no zero pivot occurs) */
    for (int k = 0; k < n; k++) {
        for (int i = k + 1; i < n; i++) {
            double factor = A[i * n + k] / A[k * n + k];
            A[i * n + k] = factor;
            for (int j = k + 1; j < n; j++)
                A[i * n + j] -= factor * A[k * n + j];
        }
    }

    double s = 0;
    for (int i = 0; i < n * n; i++) s += A[i];
    printf("%.6f\n", s);

    free(A);
    return 0;
}
