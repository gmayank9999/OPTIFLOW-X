#include <stdio.h>
#include <stdlib.h>
#define BIG 2000000000

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    long long *p = malloc(sizeof(long long) * (n + 1));
    for (int i = 0; i <= n; i++)
        if (scanf("%lld", &p[i]) != 1) return 1;

    long long *dp = malloc(sizeof(long long) * (size_t)(n + 1) * (n + 1));
    #define D(i, j) dp[(i) * (n + 1) + (j)]

    for (int i = 1; i <= n; i++) D(i, i) = 0;

    for (int len = 2; len <= n; len++) {
        for (int i = 1; i <= n - len + 1; i++) {
            int j = i + len - 1;
            long long best = (long long)BIG * BIG;
            for (int k = i; k < j; k++) {
                long long cost = D(i, k) + D(k + 1, j) + p[i - 1] * p[k] * p[j];
                if (cost < best) best = cost;
            }
            D(i, j) = best;
        }
    }

    printf("%lld\n", D(1, n));

    free(p); free(dp);
    return 0;
}
