// Line-level LCS diff producing a unified diff (3 lines of context), in
// the same format DiffView parses. Users can bring programs of a few
// thousand lines, so the common head and tail are peeled off first and the
// O(n*m) table is only built for the changed middle (capped; beyond the cap
// the middle is reported as one replaced block).
type Op = { t: " " | "-" | "+"; s: string; ai: number; bi: number };

const MAX_CELLS = 4_000_000;

function lines(text: string): string[] {
  return text.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");
}

function computeOps(A: string[], B: string[]): Op[] {
  const ops: Op[] = [];
  let head = 0;
  while (head < A.length && head < B.length && A[head] === B[head]) head++;
  let tail = 0;
  while (tail < A.length - head && tail < B.length - head && A[A.length - 1 - tail] === B[B.length - 1 - tail]) tail++;

  for (let k = 0; k < head; k++) ops.push({ t: " ", s: A[k], ai: k, bi: k });

  const a = A.slice(head, A.length - tail);
  const b = B.slice(head, B.length - tail);
  const n = a.length;
  const m = b.length;
  let i = 0;
  let j = 0;
  if (n * m > MAX_CELLS) {
    for (; i < n; i++) ops.push({ t: "-", s: a[i], ai: head + i, bi: head + j });
    for (; j < m; j++) ops.push({ t: "+", s: b[j], ai: head + i, bi: head + j });
  } else {
    const L: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let x = n - 1; x >= 0; x--)
      for (let y = m - 1; y >= 0; y--) L[x][y] = a[x] === b[y] ? L[x + 1][y + 1] + 1 : Math.max(L[x + 1][y], L[x][y + 1]);
    while (i < n && j < m) {
      if (a[i] === b[j]) ops.push({ t: " ", s: a[i], ai: head + i++, bi: head + j++ });
      else if (L[i + 1][j] >= L[i][j + 1]) ops.push({ t: "-", s: a[i], ai: head + i++, bi: head + j });
      else ops.push({ t: "+", s: b[j], ai: head + i, bi: head + j++ });
    }
    while (i < n) ops.push({ t: "-", s: a[i], ai: head + i++, bi: head + j });
    while (j < m) ops.push({ t: "+", s: b[j], ai: head + i, bi: head + j++ });
  }

  for (let k = 0; k < tail; k++) ops.push({ t: " ", s: A[A.length - tail + k], ai: A.length - tail + k, bi: B.length - tail + k });
  return ops;
}

/** 0-based indexes of lines removed from `a` and added in `b`. */
export function lineChanges(a: string, b: string): { removed: Set<number>; added: Set<number> } {
  const removed = new Set<number>();
  const added = new Set<number>();
  for (const o of computeOps(lines(a), lines(b))) {
    if (o.t === "-") removed.add(o.ai);
    if (o.t === "+") added.add(o.bi);
  }
  return { removed, added };
}

export function unifiedDiff(a: string, b: string, context = 3, name = "main.c"): string {
  const ops = computeOps(lines(a), lines(b));
  const changed = ops.map((o, k) => (o.t !== " " ? k : -1)).filter((k) => k >= 0);
  if (!changed.length) return "";
  const out: string[] = [`--- a/${name}`, `+++ b/${name}`];
  let k = 0;
  while (k < changed.length) {
    const start = Math.max(0, changed[k] - context);
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
  }
  return out.join("\n");
}
