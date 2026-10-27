"""More hand-written single-strategy variants: pure loop interchange,
algorithmic replacements, memory reuse and contiguous layout.

Each variant produces byte-identical output to its original (verified by
the sweep against the reference outputs before any row is labeled).
Imported by templates.py, so `import optiflow.ml.templates` loads both.
Raw strings so C escapes stay literal.
"""

from optiflow.ml.build_dataset import register_template

register_template("matmul_naive", "interchange", r"""
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    double *A = malloc(sizeof(double) * n * n);
    double *B = malloc(sizeof(double) * n * n);
    double *C = calloc((size_t)n * n, sizeof(double));
    for (int i = 0; i < n * n; i++) { A[i] = (i % 97) * 0.01; B[i] = (i % 89) * 0.02; }
    for (int i = 0; i < n; i++)
        for (int k = 0; k < n; k++) {
            double r = A[i * n + k];
            for (int j = 0; j < n; j++)
                C[i * n + j] += r * B[k * n + j];
        }
    double s = 0; for (int i = 0; i < n * n; i++) s += C[i];
    printf("%.6f\n", s);
    free(A); free(B); free(C); return 0;
}
""")

SORTED_CHECKSUM_MAIN = r"""
#include <stdio.h>
#include <stdlib.h>
static int cmp_int(const void *x, const void *y) {
    int a = *(const int *)x, b = *(const int *)y;
    return (a > b) - (a < b);
}
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    int *a = malloc(sizeof(int) * (size_t)(n > 0 ? n : 1));
    for (int i = 0; i < n; i++) if (scanf("%d", &a[i]) != 1) return 1;
    qsort(a, (size_t)n, sizeof(int), cmp_int);
    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (long long)a[i] * (i + 1);
    printf("%lld\n", checksum);
    free(a); return 0;
}
"""
for _pid in ("bubble_sort", "insertion_sort", "selection_sort", "quicksort_bad_pivot"):
    register_template(_pid, "algorithmic", SORTED_CHECKSUM_MAIN)

register_template("count_inversions", "algorithmic", r"""
#include <stdio.h>
#include <stdlib.h>
static long long sort_count(int *a, int *tmp, int n) {
    if (n < 2) return 0;
    int mid = n / 2;
    long long inv = sort_count(a, tmp, mid) + sort_count(a + mid, tmp, n - mid);
    int i = 0, j = mid, k = 0;
    while (i < mid && j < n) {
        if (a[i] <= a[j]) tmp[k++] = a[i++];
        else { inv += mid - i; tmp[k++] = a[j++]; }
    }
    while (i < mid) tmp[k++] = a[i++];
    while (j < n) tmp[k++] = a[j++];
    for (int t = 0; t < n; t++) a[t] = tmp[t];
    return inv;
}
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    int *a = malloc(sizeof(int) * (size_t)(n > 0 ? n : 1));
    int *tmp = malloc(sizeof(int) * (size_t)(n > 0 ? n : 1));
    for (int i = 0; i < n; i++) if (scanf("%d", &a[i]) != 1) return 1;
    printf("%lld\n", sort_count(a, tmp, n));
    free(a); free(tmp); return 0;
}
""")

register_template("palindrome_count", "algorithmic", r"""
#include <stdio.h>
#include <string.h>
static char s[60005];
int main(void) {
    if (scanf("%60004s", s) != 1) return 1;
    int n = (int)strlen(s);
    long long count = 0;
    for (int c = 0; c < n; c++) {
        for (int lo = c, hi = c; lo >= 0 && hi < n && s[lo] == s[hi]; lo--, hi++) count++;
        for (int lo = c, hi = c + 1; lo >= 0 && hi < n && s[lo] == s[hi]; lo--, hi++) count++;
    }
    printf("%lld\n", count);
    return 0;
}
""")

register_template("mergesort_mallocs", "hoist", r"""
#include <stdio.h>
#include <stdlib.h>
static int *scratch;
static void merge(int *a, int lo, int mid, int hi) {
    int i = lo, j = mid + 1, k = lo;
    while (i <= mid && j <= hi) scratch[k++] = (a[i] <= a[j]) ? a[i++] : a[j++];
    while (i <= mid) scratch[k++] = a[i++];
    while (j <= hi) scratch[k++] = a[j++];
    for (int t = lo; t <= hi; t++) a[t] = scratch[t];
}
static void mergesort(int *a, int lo, int hi) {
    if (lo >= hi) return;
    int mid = lo + (hi - lo) / 2;
    mergesort(a, lo, mid);
    mergesort(a, mid + 1, hi);
    merge(a, lo, mid, hi);
}
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    int *a = malloc(sizeof(int) * (size_t)(n > 0 ? n : 1));
    scratch = malloc(sizeof(int) * (size_t)(n > 0 ? n : 1));
    for (int i = 0; i < n; i++) if (scanf("%d", &a[i]) != 1) return 1;
    if (n > 0) mergesort(a, 0, n - 1);
    long long checksum = 0;
    for (int i = 0; i < n; i++) checksum += (long long)a[i] * (i + 1);
    printf("%lld\n", checksum);
    free(a); free(scratch); return 0;
}
""")

register_template("word_freq_linear", "algorithmic", r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MAXWORD 32
typedef struct { char word[MAXWORD]; int count; } Entry;
static unsigned long hash_str(const char *s) {
    unsigned long h = 5381;
    while (*s) h = h * 33 + (unsigned char)*s++;
    return h;
}
int main(void) {
    int n; if (scanf("%d", &n) != 1) return 1;
    Entry *table = malloc(sizeof(Entry) * (size_t)(n > 0 ? n : 1));
    size_t cap = 16; while (cap < (size_t)n * 2) cap <<= 1;
    int *slots = malloc(sizeof(int) * cap);
    for (size_t i = 0; i < cap; i++) slots[i] = -1;
    int unique = 0;
    for (int k = 0; k < n; k++) {
        char buf[MAXWORD];
        if (scanf("%31s", buf) != 1) return 1;
        size_t h = hash_str(buf) & (cap - 1);
        while (slots[h] >= 0 && strcmp(table[slots[h]].word, buf) != 0) h = (h + 1) & (cap - 1);
        if (slots[h] >= 0) {
            table[slots[h]].count++;
        } else {
            strcpy(table[unique].word, buf);
            table[unique].count = 1;
            slots[h] = unique++;   /* first-seen order preserved: the checksum depends on it */
        }
    }
    long long checksum = 0;
    for (int i = 0; i < unique; i++) checksum += (long long)table[i].count * (i + 1);
    printf("%lld\n", checksum);
    free(table); free(slots); return 0;
}
""")

register_template("linear_search_many", "algorithmic", r"""
#include <stdio.h>
#include <stdlib.h>
typedef struct { int value, index; } Pair;
static int cmp_pair(const void *x, const void *y) {
    const Pair *a = x, *b = y;
    if (a->value != b->value) return (a->value > b->value) - (a->value < b->value);
    return (a->index > b->index) - (a->index < b->index);
}
int main(void) {
    int n, q; if (scanf("%d %d", &n, &q) != 2) return 1;
    Pair *p = malloc(sizeof(Pair) * (size_t)(n > 0 ? n : 1));
    for (int i = 0; i < n; i++) { if (scanf("%d", &p[i].value) != 1) return 1; p[i].index = i; }
    qsort(p, (size_t)n, sizeof(Pair), cmp_pair);
    long long found = 0;
    for (int k = 0; k < q; k++) {
        int target; if (scanf("%d", &target) != 1) return 1;
        int lo = 0, hi = n;   /* lower_bound: first pair with value >= target */
        while (lo < hi) { int mid = lo + (hi - lo) / 2; if (p[mid].value < target) lo = mid + 1; else hi = mid; }
        if (lo < n && p[lo].value == target) found += p[lo].index + 1;   /* smallest index = first match */
    }
    printf("%lld\n", found);
    free(p); return 0;
}
""")

register_template("linked_list_traversal", "soa", r"""
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int n, passes; if (scanf("%d %d", &n, &passes) != 2) return 1;
    int *values = malloc(sizeof(int) * (size_t)(n > 0 ? n : 1));   /* contiguous instead of linked */
    for (int i = 0; i < n; i++) values[i] = (i % 991) - 495;
    long long sum = 0;
    for (int p = 0; p < passes; p++)
        for (int i = 0; i < n; i++) sum += values[i];
    printf("%lld\n", sum);
    free(values); return 0;
}
""")

register_template("substring_naive", "algorithmic", r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    static char text[3000005];
    static char pat[64];
    if (scanf("%3000004s %63s", text, pat) != 2) return 1;
    int n = (int)strlen(text), m = (int)strlen(pat);
    int fail[64]; fail[0] = 0;
    for (int i = 1, k = 0; i < m; i++) {
        while (k > 0 && pat[i] != pat[k]) k = fail[k - 1];
        if (pat[i] == pat[k]) k++;
        fail[i] = k;
    }
    long long count = 0;
    for (int i = 0, k = 0; i < n; i++) {   /* KMP: overlapping matches, same count as the naive scan */
        while (k > 0 && text[i] != pat[k]) k = fail[k - 1];
        if (text[i] == pat[k]) k++;
        if (k == m) { count++; k = fail[k - 1]; }
    }
    printf("%lld\n", count);
    return 0;
}
""")
