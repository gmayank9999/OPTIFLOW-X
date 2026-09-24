#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * n);
    double *x = malloc(sizeof(double) * (size_t)n);
    double *y = calloc((size_t)n, sizeof(double));

    for (int i = 0; i < n * n; i++) A[i] = (i % 71) * 0.01;
    for (int i = 0; i < n; i++) x[i] = (i % 13) * 0.1;

    /* column outer, row inner: strided access into A, cache-hostile */
    for (int j = 0; j < n; j++)
        for (int i = 0; i < n; i++)
            y[i] += A[i * n + j] * x[j];

    double s = 0;
    for (int i = 0; i < n; i++) s += y[i];
    printf("%.6f\n", s);

    free(A); free(x); free(y);
    return 0;
}
