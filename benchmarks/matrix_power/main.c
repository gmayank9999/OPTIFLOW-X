#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, p;
    if (scanf("%d %d", &n, &p) != 2) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * n);
    double *R = calloc((size_t)n * n, sizeof(double));
    double *tmp = malloc(sizeof(double) * (size_t)n * n);

    for (int i = 0; i < n * n; i++) A[i] = (i % 19) * 0.02;
    for (int i = 0; i < n; i++) R[i * n + i] = 1.0;  /* R = identity */

    for (int step = 0; step < p; step++) {
        for (int i = 0; i < n * n; i++) tmp[i] = 0;
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++)
                for (int k = 0; k < n; k++)
                    tmp[i * n + j] += R[i * n + k] * A[k * n + j];  /* column access on A */
        for (int i = 0; i < n * n; i++) R[i] = tmp[i];
    }

    double s = 0;
    for (int i = 0; i < n * n; i++) s += R[i];
    printf("%.6f\n", s);

    free(A); free(R); free(tmp);
    return 0;
}
