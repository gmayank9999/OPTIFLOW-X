#include <stdio.h>
#include <stdlib.h>

static void bubble_sort(int *a, int n) {
    for (int i = 0; i < n - 1; i++)
        for (int j = 0; j < n - 1 - i; j++)
            if (a[j] > a[j + 1]) { int t = a[j]; a[j] = a[j + 1]; a[j + 1] = t; }
}

static int binary_search(int *a, int n, int target) {
    int lo = 0, hi = n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (a[mid] == target) return mid;
        if (a[mid] < target) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

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
        bubble_sort(a, n);  /* re-sorts before every query: wildly redundant */
        int idx = binary_search(a, n, target);
        if (idx >= 0) found += idx + 1;
    }

    printf("%lld\n", found);

    free(a);
    return 0;
}
