#include <stdio.h>
#include <stdlib.h>
#define INF 1000000

int main(void) {
    int n, src;
    if (scanf("%d %d", &n, &src) != 2) return 1;

    int *w = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &w[i]) != 1) return 1;

    int *dist = malloc(sizeof(int) * n);
    int *visited = calloc(n, sizeof(int));
    for (int i = 0; i < n; i++) dist[i] = INF;
    dist[src] = 0;

    for (int iter = 0; iter < n; iter++) {
        int u = -1, best = INF + 1;
        for (int i = 0; i < n; i++)             /* O(n) vertex scan instead of a heap */
            if (!visited[i] && dist[i] < best) { best = dist[i]; u = i; }
        if (u == -1) break;
        visited[u] = 1;
        for (int v = 0; v < n; v++)
            if (w[u * n + v] > 0 && dist[u] + w[u * n + v] < dist[v])
                dist[v] = dist[u] + w[u * n + v];
    }

    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (dist[i] >= INF) ? 0 : dist[i];
    printf("%lld\n", checksum);

    free(w); free(dist); free(visited);
    return 0;
}
