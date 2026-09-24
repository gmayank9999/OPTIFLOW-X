# Loop interchange

When: nested loops over 2D/3D arrays where the innermost loop variable
indexes a non-trailing dimension (stride_mismatch=1), e.g. B[k*n+j] with
k as the innermost loop variable. This produces a large stride between
consecutive accesses and a cache miss on nearly every iteration.

How: reorder the loop nest so the innermost loop's variable matches the
last index of the array subscripts touched inside it. For matrix
multiply C[i][j] += A[i][k]*B[k][j], swapping to i-k-j order makes both
A and B accessed row-wise in the inner loop.

Pitfalls: only valid when loop iterations are independent (no carried
dependency that depends on the original order); check for reductions
that assume a specific accumulation order under strict float semantics.

Expected gain: 2-6x on classic matmul-shaped loops; much smaller on
loops that are already stride-1.
