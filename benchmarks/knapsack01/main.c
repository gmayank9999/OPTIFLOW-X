#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, W;
    if (scanf("%d %d", &n, &W) != 2) return 1;

    int *wt = malloc(sizeof(int) * n);
    int *val = malloc(sizeof(int) * n);
    for (int i = 0; i < n; i++)
        if (scanf("%d %d", &wt[i], &val[i]) != 2) return 1;

    int *dp = calloc((size_t)(n + 1) * (W + 1), sizeof(int));
    #define D(i, w) dp[(i) * (W + 1) + (w)]

    for (int i = 1; i <= n; i++)
        for (int w = 0; w <= W; w++) {
            D(i, w) = D(i - 1, w);
            if (wt[i - 1] <= w) {
                int cand = D(i - 1, w - wt[i - 1]) + val[i - 1];
                if (cand > D(i, w)) D(i, w) = cand;
            }
        }

    printf("%d\n", D(n, W));

    free(wt); free(val); free(dp);
    return 0;
}
