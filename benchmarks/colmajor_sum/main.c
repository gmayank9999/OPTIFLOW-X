#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * n);
    for (int i = 0; i < n * n; i++) A[i] = (i % 113) * 0.01;

    double s = 0;
    for (int j = 0; j < n; j++)
        for (int i = 0; i < n; i++)
            s += A[i * n + j];  /* column-major traversal of row-major storage: cache-hostile */

    printf("%.6f\n", s);
    free(A);
    return 0;
}
