#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *a = malloc(sizeof(int) * (size_t)n);
    for (int i = 0; i < n; i++)
        if (scanf("%d", &a[i]) != 1) return 1;

    long long inversions = 0;
    for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)
            if (a[i] > a[j]) inversions++;

    printf("%lld\n", inversions);

    free(a);
    return 0;
}
