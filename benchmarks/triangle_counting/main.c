#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *adj = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &adj[i]) != 1) return 1;

    long long triangles = 0;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)
            if (adj[i * n + j])
                for (int k = j + 1; k < n; k++)
                    if (adj[i * n + k] && adj[j * n + k])
                        triangles++;

    printf("%lld\n", triangles);

    free(adj);
    return 0;
}
