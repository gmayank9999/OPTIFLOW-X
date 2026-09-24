# Algorithmic memoization

When: has_recursion is true and the recursive calls repeat overlapping
subproblems (classic case: naive Fibonacci, or any textbook recursive DP
without a table), causing exponential blowup from re-solving the same
input.

How: add a table (array or hash map) keyed on the function's arguments;
before recursing, check whether the result is already cached. For small
bounded integer arguments, a flat array is faster than a hash map.

Pitfalls: memoization changes the space complexity, sometimes
significantly; for recursion depths that already fit comfortably in the
time budget, the added bookkeeping can make small inputs slower even
while making large inputs dramatically faster. Converting to an
iterative bottom-up DP avoids call-stack overhead entirely and is
usually the better target once the recurrence is identified.

Expected gain: exponential-to-polynomial, often 10x or more on inputs
large enough for the naive version to matter at all.
