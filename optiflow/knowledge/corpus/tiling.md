# Loop tiling (blocking)

When: nested loops over 2D arrays, working set bigger than L1/L2, high
L1/LLC miss rate, stride_mismatch=1 even after considering interchange.

How: split each loop into a block loop and an inner loop, block size
16-64 for doubles (tune to L1 size / (array_count * element_size)).

Pitfalls: sizes not divisible by the tile size skip or overrun elements;
use min(ii+T, n) as the inner bound, never assume n % T == 0. Do not tile
loops with a carried dependency that would change the order of a
floating-point reduction when compare mode is exact.

Example: naive matmul

    for (i = 0; i < n; i++)
      for (j = 0; j < n; j++)
        for (k = 0; k < n; k++)
          C[i*n+j] += A[i*n+k] * B[k*n+j];

becomes, with tile size T:

    for (ii = 0; ii < n; ii += T)
      for (jj = 0; jj < n; jj += T)
        for (kk = 0; kk < n; kk += T)
          for (i = ii; i < min(ii+T, n); i++)
            for (j = jj; j < min(jj+T, n); j++)
              for (k = kk; k < min(kk+T, n); k++)
                C[i*n+j] += A[i*n+k] * B[k*n+j];

Expected gain: 2-6x on matmul-shaped loops with n >= 256, on top of
whatever interchange already gave.
