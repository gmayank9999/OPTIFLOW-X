# Compiler flags

When: almost always worth trying first; especially when the profile shows
high instruction count with no single dominant loop, or when the loop
body is already vectorizable but not marked as such.

How: escalate from -O2 to -O3, then add -march=native for CPU-specific
SIMD, -funroll-loops for tight inner loops, -flto for cross-function
inlining. Try gcc and clang independently since their auto-vectorizers
differ.

Pitfalls: -Ofast and -ffast-math reorder floating point operations and
can change output beyond float tolerance; only use them when compare
mode is float_tol, and log that they were used. -march=native ties the
binary to the build machine's CPU, irrelevant for a benchmark run on one
fixed machine but worth naming if the report claims portability.

Expected gain: 1.1-2x depending on how much the baseline already
resembles -O2 output; larger when the source has obvious but unmarked
vectorization opportunities.
