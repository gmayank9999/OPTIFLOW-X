// Line-level LCS diff producing a unified diff (3 lines of context), in
// the same format DiffView parses. The benchmark sources are < 200 lines,
// so the O(n*m) table is a few tens of thousands of cells at most.
export function unifiedDiff(a: string, b: string, context = 3): string {
  const A = a.replace(/\n$/, "").split("\n");
  const B = b.replace(/\n$/, "").split("\n");
  const n = A.length;
  const m = B.length;
  const L: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);

  type Op = { t: " " | "-" | "+"; s: string; ai: number; bi: number };
  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) ops.push({ t: " ", s: A[i], ai: i++, bi: j++ });
    else if (L[i + 1][j] >= L[i][j + 1]) ops.push({ t: "-", s: A[i], ai: i++, bi: j });
    else ops.push({ t: "+", s: B[j], ai: i, bi: j++ });
  }
  while (i < n) ops.push({ t: "-", s: A[i], ai: i++, bi: j });
  while (j < m) ops.push({ t: "+", s: B[j], ai: i, bi: j++ });

  const changed = ops.map((o, k) => (o.t !== " " ? k : -1)).filter((k) => k >= 0);
  if (!changed.length) return "";
  const out: string[] = ["--- a/main.c", "+++ b/main.c"];
  let k = 0;
  while (k < changed.length) {
    let start = Math.max(0, changed[k] - context);
    let end = Math.min(ops.length - 1, changed[k] + context);
    while (k + 1 < changed.length && changed[k + 1] - context <= end + 1) {
      k++;
      end = Math.min(ops.length - 1, changed[k] + context);
    }
    const hunk = ops.slice(start, end + 1);
    const oldStart = hunk[0].ai + 1;
    const newStart = hunk[0].bi + 1;
    const oldLen = hunk.filter((o) => o.t !== "+").length;
    const newLen = hunk.filter((o) => o.t !== "-").length;
    out.push(`@@ -${oldStart},${oldLen} +${newStart},${newLen} @@`);
    for (const o of hunk) out.push(o.t + o.s);
    k++;
    start = end + 1;
  }
  return out.join("\n");
}
