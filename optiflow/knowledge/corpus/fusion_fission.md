# Loop fusion and fission

When fusion: two consecutive loops iterate over the same range and
touch the same array; fusing them into one loop reuses data already in
cache instead of streaming the array through memory twice.

When fission: a single loop mixes two unrelated computations, one
vectorizable and one not (e.g. a function call), and splitting them lets
the vectorizable part get vectorized.

How (fusion): merge the bodies of two loops with identical bounds into
one, preserving execution order for a given index if there is a
dependency between the loops.

How (fission): split a loop body into two loops with the same bounds,
one containing only the part with no function calls or dependencies.

Pitfalls: fusion is invalid if the second loop reads a value the first
loop writes at a later index than the one currently being processed
(a loop-carried dependency across the fused body).

Expected gain: 1.2-2x, workload dependent.
