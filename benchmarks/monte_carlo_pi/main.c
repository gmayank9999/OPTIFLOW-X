#include <stdio.h>

/* deterministic LCG so results are identical across platforms/libc
   versions, unlike rand() whose sequence is implementation-defined */
static unsigned long state;

static double next_rand(void) {
    state = state * 6364136223846793005UL + 1442695040888963407UL;
    return (double)((state >> 11) & 0x1FFFFFFFFFFFFFUL) / (double)(1UL << 53);
}

int main(void) {
    long n;
    unsigned long seed;
    if (scanf("%ld %lu", &n, &seed) != 2) return 1;
    state = seed;

    long inside = 0;
    for (long i = 0; i < n; i++) {
        double x = next_rand() * 2.0 - 1.0;
        double y = next_rand() * 2.0 - 1.0;
        if (x * x + y * y <= 1.0) inside++;
    }

    printf("%ld\n", inside);
    return 0;
}
