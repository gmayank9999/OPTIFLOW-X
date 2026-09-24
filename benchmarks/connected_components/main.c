#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *adj = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &adj[i]) != 1) return 1;

    int *visited = calloc(n, sizeof(int));
    int *queue = malloc(sizeof(int) * n);
    int components = 0;
    long long size_sum = 0;

    for (int s = 0; s < n; s++) {
        if (visited[s]) continue;
        components++;
        int qh = 0, qt = 0, comp_size = 0;
        visited[s] = 1;
        queue[qt++] = s;
        while (qh < qt) {
            int u = queue[qh++];
            comp_size++;
            for (int v = 0; v < n; v++)
                if (adj[u * n + v] && !visited[v]) {
                    visited[v] = 1;
                    queue[qt++] = v;
                }
        }
        size_sum += (long long)comp_size * components;
    }

    printf("%d %lld\n", components, size_sum);

    free(adj); free(visited); free(queue);
    return 0;
}
