# Algorithmic replacement

When: the profile shows the time is spent in work whose *amount* is the
problem rather than how it touches memory: quadratic sorts (bubble,
insertion, selection) on large inputs, re-sorting or re-scanning the
same data for every query, a linear scan where a lookup table fits,
first-element-pivot quicksort on sorted input, counting inversions with
two nested loops. Loop transformations and flags only shave constant
factors here; a better algorithm changes the complexity class.

How: identify the exact output the program prints, then pick an
algorithm that provably produces the same output: an O(n log n) sort
(merge sort, or qsort with a total-order comparator) for O(n^2) sorts;
sort once and binary-search per query instead of sorting per query; a
merge-sort-based inversion count; a median-of-three or random-free
deterministic pivot; a direct-indexed or hashed table for word counts.

Pitfalls: output must stay byte-identical. Stable vs unstable sorting
matters when ties are printed with their original positions. Integer
overflow changes when sums are reordered over long long vs int. Keep
the same tie-breaking rules, the same counting of duplicates, and the
same handling of n=0 and n=1. Do not introduce randomness.

Expected gain: often 10x-1000x on the benchmark input, because the
complexity class changes; the gain grows with input size.
