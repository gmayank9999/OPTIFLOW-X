#include <stdio.h>
#include <stdlib.h>

static void merge(int *a, int lo, int mid, int hi) {
    int n1 = mid - lo + 1, n2 = hi - mid;
    int *left = malloc(sizeof(int) * n1);   /* fresh malloc on every merge call */
    int *right = malloc(sizeof(int) * n2);

    for (int i = 0; i < n1; i++) left[i] = a[lo + i];
    for (int i = 0; i < n2; i++) right[i] = a[mid + 1 + i];

    int i = 0, j = 0, k = lo;
    while (i < n1 && j < n2) a[k++] = (left[i] <= right[j]) ? left[i++] : right[j++];
    while (i < n1) a[k++] = left[i++];
    while (j < n2) a[k++] = right[j++];

    free(left);
    free(right);
}

static void mergesort(int *a, int lo, int hi) {
    if (lo >= hi) return;
    int mid = lo + (hi - lo) / 2;
    mergesort(a, lo, mid);
    mergesort(a, mid + 1, hi);
    merge(a, lo, mid, hi);
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *a = malloc(sizeof(int) * (size_t)n);
    for (int i = 0; i < n; i++)
        if (scanf("%d", &a[i]) != 1) return 1;

    if (n > 0) mergesort(a, 0, n - 1);

    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (long long)a[i] * (i + 1);
    printf("%lld\n", checksum);

    free(a);
    return 0;
}
