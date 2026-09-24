#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * n);
    for (int i = 0; i < n * n; i++) A[i] = (i % 137) * 0.01;

    double sumsq = 0;
    for (int j = 0; j < n; j++)
        for (int i = 0; i < n; i++)
            sumsq += A[i * n + j] * A[i * n + j];  /* column-major traversal: cache-hostile */

    printf("%.6f\n", sqrt(sumsq));
    free(A);
    return 0;
}
