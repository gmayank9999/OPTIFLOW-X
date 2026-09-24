#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char a[8005], b[8005];

int main(void) {
    if (scanf("%8004s %8004s", a, b) != 2) return 1;

    int n = (int)strlen(a), m = (int)strlen(b);
    int *dp = calloc((size_t)(n + 1) * (m + 1), sizeof(int));

    for (int i = 1; i <= n; i++)
        for (int j = 1; j <= m; j++) {
            if (a[i - 1] == b[j - 1]) {
                dp[i * (m + 1) + j] = dp[(i - 1) * (m + 1) + (j - 1)] + 1;
            } else {
                int x = dp[(i - 1) * (m + 1) + j];
                int y = dp[i * (m + 1) + (j - 1)];
                dp[i * (m + 1) + j] = x > y ? x : y;
            }
        }

    printf("%d\n", dp[n * (m + 1) + m]);
    free(dp);
    return 0;
}
