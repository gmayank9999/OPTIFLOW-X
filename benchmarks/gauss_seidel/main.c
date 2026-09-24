#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, steps;
    if (scanf("%d %d", &n, &steps) != 2) return 1;

    double *u = calloc((size_t)n * n, sizeof(double));

    for (int i = 0; i < n; i++) { u[i * n] = 1.0; u[i * n + n - 1] = 1.0; }
    for (int j = 0; j < n; j++) { u[j] = 1.0; u[(n - 1) * n + j] = 1.0; }

    /* in-place update: each element depends on already-updated neighbors
       in the same pass, so it cannot be tiled the same way as Jacobi
       without changing the convergence sequence */
    for (int s = 0; s < steps; s++) {
        for (int i = 1; i < n - 1; i++)
            for (int j = 1; j < n - 1; j++)
                u[i * n + j] = 0.25 * (u[(i - 1) * n + j] + u[(i + 1) * n + j]
                                      + u[i * n + j - 1] + u[i * n + j + 1]);
    }

    double sum = 0;
    for (int i = 0; i < n * n; i++) sum += u[i];
    printf("%.6f\n", sum);

    free(u);
    return 0;
}
