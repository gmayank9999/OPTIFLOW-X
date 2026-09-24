#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, src;
    if (scanf("%d %d", &n, &src) != 2) return 1;

    int *adj = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &adj[i]) != 1) return 1;

    int *dist = malloc(sizeof(int) * n);
    int *queue = malloc(sizeof(int) * n);
    for (int i = 0; i < n; i++) dist[i] = -1;

    int qh = 0, qt = 0;
    dist[src] = 0;
    queue[qt++] = src;

    while (qh < qt) {
        int u = queue[qh++];
        for (int v = 0; v < n; v++) {          /* O(n) scan per node: adjacency matrix BFS */
            if (adj[u * n + v] && dist[v] == -1) {
                dist[v] = dist[u] + 1;
                queue[qt++] = v;
            }
        }
    }

    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (dist[i] + 1);
    printf("%lld\n", checksum);

    free(adj); free(dist); free(queue);
    return 0;
}
