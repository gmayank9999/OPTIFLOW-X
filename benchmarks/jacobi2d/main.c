#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, iters;
    if (scanf("%d %d", &n, &iters) != 2) return 1;

    double *u = calloc((size_t)n * n, sizeof(double));
    double *unew = calloc((size_t)n * n, sizeof(double));

    for (int i = 0; i < n; i++) { u[i * n] = 1.0; u[i * n + n - 1] = 1.0; }
    for (int j = 0; j < n; j++) { u[j] = 1.0; u[(n - 1) * n + j] = 1.0; }

    for (int it = 0; it < iters; it++) {
        for (int i = 1; i < n - 1; i++)
            for (int j = 1; j < n - 1; j++)
                unew[i * n + j] = 0.25 * (u[(i - 1) * n + j] + u[(i + 1) * n + j]
                                         + u[i * n + j - 1] + u[i * n + j + 1]);
        for (int i = 1; i < n - 1; i++)
            for (int j = 1; j < n - 1; j++)
                u[i * n + j] = unew[i * n + j];
    }

    double s = 0;
    for (int i = 0; i < n * n; i++) s += u[i];
    printf("%.6f\n", s);

    free(u); free(unew);
    return 0;
}
