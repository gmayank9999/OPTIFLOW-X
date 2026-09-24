#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, steps;
    if (scanf("%d %d", &n, &steps) != 2) return 1;

    double *u = calloc((size_t)n, sizeof(double));
    double *unew = calloc((size_t)n, sizeof(double));
    double alpha = 0.1;

    u[0] = 100.0;
    u[n - 1] = 50.0;

    for (int s = 0; s < steps; s++) {
        for (int i = 1; i < n - 1; i++)
            unew[i] = u[i] + alpha * (u[i - 1] - 2 * u[i] + u[i + 1]);
        for (int i = 1; i < n - 1; i++)
            u[i] = unew[i];
    }

    double sum = 0;
    for (int i = 0; i < n; i++) sum += u[i];
    printf("%.6f\n", sum);

    free(u); free(unew);
    return 0;
}
