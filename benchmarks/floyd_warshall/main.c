#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    int *d = malloc(sizeof(int) * (size_t)n * n);
    for (int i = 0; i < n * n; i++)
        if (scanf("%d", &d[i]) != 1) return 1;

    for (int k = 0; k < n; k++)
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++)
                if (d[i * n + k] + d[k * n + j] < d[i * n + j])
                    d[i * n + j] = d[i * n + k] + d[k * n + j];

    long long checksum = 0;
    for (int i = 0; i < n * n; i++) checksum += d[i] % 97;
    printf("%lld\n", checksum);

    free(d);
    return 0;
}
