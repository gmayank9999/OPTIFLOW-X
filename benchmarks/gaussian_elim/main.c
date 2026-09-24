#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *A = malloc(sizeof(double) * (size_t)n * n);
    double *b = malloc(sizeof(double) * (size_t)n);
    double *x = malloc(sizeof(double) * (size_t)n);

    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++)
            A[i * n + j] = (i == j) ? (n * 3.0) : ((i + j) % 5 + 1) * 0.1;
        b[i] = (i % 17) * 0.5 + 1.0;
    }

    for (int k = 0; k < n; k++) {
        for (int i = k + 1; i < n; i++) {
            double factor = A[i * n + k] / A[k * n + k];
            for (int j = k; j < n; j++)
                A[i * n + j] -= factor * A[k * n + j];
            b[i] -= factor * b[k];
        }
    }

    for (int i = n - 1; i >= 0; i--) {
        double sum = b[i];
        for (int j = i + 1; j < n; j++)
            sum -= A[i * n + j] * x[j];
        x[i] = sum / A[i * n + i];
    }

    double s = 0;
    for (int i = 0; i < n; i++) s += x[i];
    printf("%.6f\n", s);

    free(A); free(b); free(x);
    return 0;
}
