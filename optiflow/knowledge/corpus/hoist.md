# Hoisting and strength reduction

When: a computation inside a loop does not depend on the loop variable
(loop-invariant), or uses multiplication where an equivalent running sum
would do (e.g. an index expression recomputed every iteration, or a
string-length call in a loop condition).

How: move loop-invariant expressions above the loop into a local
variable; replace repeated-multiplication index patterns with an
incrementally updated index variable; cache strlen() results before the
loop instead of recomputing them on every condition check.

Pitfalls: only hoist expressions that are provably invariant under the
loop's actual body, not ones that merely look invariant; aliasing can
make something appear invariant when a pointer write inside the loop
could change it.

Expected gain: modest alone (1.05-1.2x), but removes a compiler
optimization barrier that can unlock larger gains from other
transformations, most obviously the strlen-in-loop-condition case.
