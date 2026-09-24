#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char a[8005], b[8005];

int main(void) {
    if (scanf("%8004s %8004s", a, b) != 2) return 1;

    int n = (int)strlen(a), m = (int)strlen(b);
    int *dp = malloc(sizeof(int) * (size_t)(n + 1) * (m + 1));
    #define D(i, j) dp[(i) * (m + 1) + (j)]

    for (int i = 0; i <= n; i++) D(i, 0) = i;
    for (int j = 0; j <= m; j++) D(0, j) = j;

    for (int i = 1; i <= n; i++)
        for (int j = 1; j <= m; j++) {
            if (a[i - 1] == b[j - 1]) {
                D(i, j) = D(i - 1, j - 1);
            } else {
                int ins = D(i, j - 1), del = D(i - 1, j), sub = D(i - 1, j - 1);
                int best = ins < del ? ins : del;
                best = best < sub ? best : sub;
                D(i, j) = best + 1;
            }
        }

    printf("%d\n", D(n, m));
    free(dp);
    return 0;
}
