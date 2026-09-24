#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * n * n);
    double *B = malloc(sizeof(double) * n * n);

    for (int i = 0; i < n * n; i++) A[i] = (i % 131) * 0.01;

    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            B[j * n + i] = A[i * n + j];  /* writes to B are cache-hostile */

    double s = 0;
    for (int i = 0; i < n * n; i++) s += B[i] * (i % 7 + 1);
    printf("%.6f\n", s);

    free(A); free(B);
    return 0;
}
