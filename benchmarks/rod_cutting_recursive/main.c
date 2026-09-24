#include <stdio.h>
#include <stdlib.h>

static int *price;

static int cut_rod(int n) {
    if (n <= 0) return 0;
    int best = -1;
    for (int i = 1; i <= n; i++) {
        int val = price[i] + cut_rod(n - i);  /* no memo: recomputes every subproblem repeatedly */
        if (val > best) best = val;
    }
    return best;
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    price = malloc(sizeof(int) * (n + 1));
    price[0] = 0;
    for (int i = 1; i <= n; i++) price[i] = 2 + (i * 3) % 7;

    printf("%d\n", cut_rod(n));

    free(price);
    return 0;
}
