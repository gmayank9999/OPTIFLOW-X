#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *a = malloc(sizeof(int) * (size_t)n);
    for (int i = 0; i < n; i++)
        if (scanf("%d", &a[i]) != 1) return 1;

    for (int i = 0; i < n - 1; i++) {
        int min_idx = i;
        for (int j = i + 1; j < n; j++)
            if (a[j] < a[min_idx]) min_idx = j;
        if (min_idx != i) {
            int t = a[i]; a[i] = a[min_idx]; a[min_idx] = t;
        }
    }

    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (long long)a[i] * (i + 1);
    printf("%lld\n", checksum);

    free(a);
    return 0;
}
