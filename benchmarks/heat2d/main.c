#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, steps;
    if (scanf("%d %d", &n, &steps) != 2) return 1;

    double *u = calloc((size_t)n * n, sizeof(double));
    double *unew = calloc((size_t)n * n, sizeof(double));
    double alpha = 0.05;

    for (int i = 0; i < n; i++) { u[i * n] = 80.0; u[i * n + n - 1] = 20.0; }

    for (int s = 0; s < steps; s++) {
        for (int i = 1; i < n - 1; i++)
            for (int j = 1; j < n - 1; j++)
                unew[i * n + j] = u[i * n + j] + alpha * (
                    u[(i - 1) * n + j] + u[(i + 1) * n + j] +
                    u[i * n + j - 1] + u[i * n + j + 1] - 4 * u[i * n + j]);
        for (int i = 1; i < n - 1; i++)
            for (int j = 1; j < n - 1; j++)
                u[i * n + j] = unew[i * n + j];
    }

    double sum = 0;
    for (int i = 0; i < n * n; i++) sum += u[i];
    printf("%.6f\n", sum);

    free(u); free(unew);
    return 0;
}
