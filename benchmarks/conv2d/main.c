#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    double *img = malloc(sizeof(double) * (size_t)n * n);
    double *out = calloc((size_t)n * n, sizeof(double));
    double kernel[3][3] = {{1,0,-1},{2,0,-2},{1,0,-1}};

    for (int i = 0; i < n * n; i++) img[i] = (i % 251) * 0.01;

    for (int i = 1; i < n - 1; i++)
        for (int j = 1; j < n - 1; j++) {
            double acc = 0;
            for (int ki = -1; ki <= 1; ki++)
                for (int kj = -1; kj <= 1; kj++)
                    acc += img[(i + ki) * n + (j + kj)] * kernel[ki + 1][kj + 1];
            out[i * n + j] = acc;
        }

    double s = 0;
    for (int i = 0; i < n * n; i++) s += out[i];
    printf("%.6f\n", s);

    free(img); free(out);
    return 0;
}
