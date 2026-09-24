#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * n * n);
    double *B = malloc(sizeof(double) * n * n);
    double *C = calloc((size_t)n * n, sizeof(double));

    for (int i = 0; i < n * n; i++) {
        A[i] = (i % 97) * 0.01;
        B[i] = (i % 89) * 0.02;
    }

    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            for (int k = 0; k < n; k++)
                C[i * n + j] += A[i * n + k] * B[k * n + j];  /* column access on B: cache-hostile */

    double s = 0;
    for (int i = 0; i < n * n; i++) s += C[i];
    printf("%.6f\n", s);

    free(A); free(B); free(C);
    return 0;
}
