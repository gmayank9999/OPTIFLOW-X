#include <stdio.h>
#include <string.h>

#define MAXLEN 64

static void reverse_str(char *s, int n) {
    for (int i = 0; i < n / 2; i++) {
        char t = s[i]; s[i] = s[n - 1 - i]; s[n - 1 - i] = t;
    }
}

int main(void) {
    int n, reps;
    if (scanf("%d %d", &n, &reps) != 2) return 1;

    static char strs[20005][MAXLEN];
    for (int i = 0; i < n; i++)
        if (scanf("%63s", strs[i]) != 1) return 1;

    long long checksum = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < n; i++) {
            int len = (int)strlen(strs[i]);   /* strlen recomputed every rep instead of cached */
            reverse_str(strs[i], len);
            checksum += (unsigned char)strs[i][0];
        }
    }

    printf("%lld\n", checksum);
    return 0;
}
