#include <stdio.h>
#include <stdlib.h>

static int partition(int *a, int lo, int hi) {
    int pivot = a[hi];  /* always last element: O(n) unbalanced split on sorted input */
    int i = lo - 1;
    for (int j = lo; j < hi; j++) {
        if (a[j] <= pivot) {
            i++;
            int t = a[i]; a[i] = a[j]; a[j] = t;
        }
    }
    int t = a[i + 1]; a[i + 1] = a[hi]; a[hi] = t;
    return i + 1;
}

static void quicksort(int *a, int lo, int hi) {
    if (lo >= hi) return;
    int p = partition(a, lo, hi);
    quicksort(a, lo, p - 1);
    quicksort(a, p + 1, hi);
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *a = malloc(sizeof(int) * (size_t)n);
    for (int i = 0; i < n; i++)
        if (scanf("%d", &a[i]) != 1) return 1;

    quicksort(a, 0, n - 1);

    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (long long)a[i] * (i + 1);
    printf("%lld\n", checksum);

    free(a);
    return 0;
}
