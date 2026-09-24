#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    static char s[2000005];
    if (scanf("%2000004s", s) != 1) return 1;

    char *out = malloc((size_t)strlen(s) * 2 + 8);
    int outlen = 0;
    long long run_count_sum = 0;

    int i = 0;
    while (i < (int)strlen(s)) {   /* strlen recomputed on every outer-loop check */
        int j = i;
        while (j < (int)strlen(s) && s[j] == s[i]) j++;   /* and on every inner-loop check too */
        int run_len = j - i;
        run_count_sum += run_len;

        char numbuf[16];
        int nl = sprintf(numbuf, "%d", run_len);
        for (int k = 0; k < nl; k++) out[outlen++] = numbuf[k];
        out[outlen++] = s[i];

        i = j;
    }
    out[outlen] = '\0';

    printf("%d %lld\n", outlen, run_count_sum);

    free(out);
    return 0;
}
