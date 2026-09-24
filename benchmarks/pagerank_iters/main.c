#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, iters;
    if (scanf("%d %d", &n, &iters) != 2) return 1;

    int *adj = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &adj[i]) != 1) return 1;

    int *outdeg = calloc(n, sizeof(int));
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            if (adj[i * n + j]) outdeg[i]++;

    double *rank = malloc(sizeof(double) * n);
    double *newrank = malloc(sizeof(double) * n);
    double damping = 0.85;
    for (int i = 0; i < n; i++) rank[i] = 1.0 / n;

    for (int it = 0; it < iters; it++) {
        for (int i = 0; i < n; i++) newrank[i] = (1.0 - damping) / n;
        for (int j = 0; j < n; j++) {           /* dense scan over all (i, j) pairs each iteration */
            if (outdeg[j] == 0) continue;
            for (int i = 0; i < n; i++)
                if (adj[j * n + i])
                    newrank[i] += damping * rank[j] / outdeg[j];
        }
        for (int i = 0; i < n; i++) rank[i] = newrank[i];
    }

    double sum = 0;
    for (int i = 0; i < n; i++) sum += rank[i];
    printf("%.6f\n", sum);

    free(adj); free(outdeg); free(rank); free(newrank);
    return 0;
}
