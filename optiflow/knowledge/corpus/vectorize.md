# Vectorization

When: a tight inner loop with no loop-carried dependency, doing the same
arithmetic on consecutive array elements, that the compiler is not
already auto-vectorizing (check with -fopt-info-vec or
-Rpass=loop-vectorize).

How: remove pointer aliasing ambiguity with __restrict__, add
#pragma omp simd (or #pragma GCC ivdep) above the loop, ensure the trip
count doesn't depend on data computed inside the loop.

Pitfalls: aliasing pointers (two unrestricted pointers that could
overlap) block auto-vectorization silently; the compiler will not warn,
it just won't vectorize. Reductions need an explicit reduction clause or
the compiler may refuse to reorder them.

Expected gain: 2-4x on arithmetic-heavy loops over contiguous arrays.
