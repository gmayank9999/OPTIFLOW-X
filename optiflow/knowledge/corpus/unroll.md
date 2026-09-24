# Loop unrolling

When: a tight inner loop with high iteration count and low per-iteration
work, where branch/compare overhead is a meaningful fraction of the
loop body.

How: repeat the loop body 2-8 times per iteration, adjusting the
increment and adding a remainder loop for counts not divisible by the
unroll factor. -funroll-loops asks the compiler to do this automatically
and is usually preferable to doing it by hand.

Pitfalls: manual unrolling that gets the remainder loop wrong silently
drops the last few iterations; always test on a size that doesn't divide
evenly by the unroll factor.

Expected gain: 1.1-1.5x, mostly on loops that are not already
vectorized; small or negative when combined with vectorization, since
the compiler's own vectorizer often unrolls internally.
