#include <stdio.h>
#include <stdlib.h>
#define INF 1000000000

int main(void) {
    int n, amount;
    if (scanf("%d %d", &n, &amount) != 2) return 1;

    int *coins = malloc(sizeof(int) * n);
    for (int i = 0; i < n; i++)
        if (scanf("%d", &coins[i]) != 1) return 1;

    int *dp = malloc(sizeof(int) * (amount + 1));
    dp[0] = 0;
    for (int a = 1; a <= amount; a++) dp[a] = INF;

    for (int a = 1; a <= amount; a++)
        for (int i = 0; i < n; i++)
            if (coins[i] <= a && dp[a - coins[i]] + 1 < dp[a])
                dp[a] = dp[a - coins[i]] + 1;

    printf("%d\n", dp[amount] >= INF ? -1 : dp[amount]);

    free(coins); free(dp);
    return 0;
}
