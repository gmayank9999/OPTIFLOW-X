#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    static char text[3000005];
    static char pat[64];
    if (scanf("%3000004s %63s", text, pat) != 2) return 1;

    int n = (int)strlen(text), m = (int)strlen(pat);
    long long count = 0;

    for (int i = 0; i + m <= n; i++) {
        int j = 0;
        while (j < m && text[i + j] == pat[j]) j++;
        if (j == m) count++;
    }

    printf("%lld\n", count);
    return 0;
}
