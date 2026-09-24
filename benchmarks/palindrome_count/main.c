#include <stdio.h>
#include <string.h>

static char s[60005];

static int is_palindrome(int lo, int hi) {
    while (lo < hi) {
        if (s[lo] != s[hi]) return 0;
        lo++; hi--;
    }
    return 1;
}

int main(void) {
    if (scanf("%60004s", s) != 1) return 1;
    int n = (int)strlen(s);

    long long count = 0;
    for (int i = 0; i < n; i++)
        for (int j = i; j < n; j++)
            if (is_palindrome(i, j)) count++;   /* O(n^3): no expansion-around-center or DP */

    printf("%lld\n", count);
    return 0;
}
