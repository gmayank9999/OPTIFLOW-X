#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n, q;
    if (scanf("%d %d", &n, &q) != 2) return 1;

    int *a = malloc(sizeof(int) * (size_t)n);
    for (int i = 0; i < n; i++)
        if (scanf("%d", &a[i]) != 1) return 1;

    long long found = 0;
    for (int k = 0; k < q; k++) {
        int target;
        if (scanf("%d", &target) != 1) return 1;
        for (int i = 0; i < n; i++) {
            if (a[i] == target) { found += i + 1; break; }
        }
    }

    printf("%lld\n", found);

    free(a);
    return 0;
}
