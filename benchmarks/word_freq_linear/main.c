#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAXWORD 32

typedef struct { char word[MAXWORD]; int count; } Entry;

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;

    Entry *table = malloc(sizeof(Entry) * n);
    int unique = 0;

    for (int k = 0; k < n; k++) {
        char buf[MAXWORD];
        if (scanf("%31s", buf) != 1) return 1;

        int found = -1;
        for (int i = 0; i < unique; i++)          /* linear scan instead of a hash map */
            if (strcmp(table[i].word, buf) == 0) { found = i; break; }

        if (found >= 0) {
            table[found].count++;
        } else {
            strcpy(table[unique].word, buf);
            table[unique].count = 1;
            unique++;
        }
    }

    long long checksum = 0;
    for (int i = 0; i < unique; i++) checksum += (long long)table[i].count * (i + 1);
    printf("%lld\n", checksum);

    free(table);
    return 0;
}
