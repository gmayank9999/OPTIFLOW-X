#include <stdio.h>
#include <stdlib.h>

static int n;
static int *adj;
static int *visited;
static long long order_sum;
static int counter;

static void dfs(int u) {
    visited[u] = 1;
    counter++;
    order_sum += (long long)u * counter;
    for (int v = 0; v < n; v++)
        if (adj[u * n + v] && !visited[v])
            dfs(v);
}

int main(void) {
    int src;
    if (scanf("%d %d", &n, &src) != 2) return 1;

    adj = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &adj[i]) != 1) return 1;

    visited = calloc(n, sizeof(int));
    order_sum = 0;
    counter = 0;
    dfs(src);

    printf("%lld\n", order_sum);

    free(adj); free(visited);
    return 0;
}
