"use client";

import { highlightLine } from "@/lib/highlight";
import { cx } from "@/lib/format";

type Row = { kind: "ctx" | "add" | "del" | "hunk"; text: string; old?: number; new?: number };

function parse(diff: string): Row[] {
  const rows: Row[] = [];
  let o = 0;
  let n = 0;
  for (const line of diff.split("\n")) {
    if (line.startsWith("---") || line.startsWith("+++")) continue;
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/.exec(line);
    if (hunk) {
      o = Number(hunk[1]);
      n = Number(hunk[2]);
      rows.push({ kind: "hunk", text: line });
    } else if (line.startsWith("+")) rows.push({ kind: "add", text: line.slice(1), new: n++ });
    else if (line.startsWith("-")) rows.push({ kind: "del", text: line.slice(1), old: o++ });
    else if (line.startsWith(" ")) rows.push({ kind: "ctx", text: line.slice(1), old: o++, new: n++ });
  }
  return rows;
}

export function DiffView({ diff, maxHeight = 520 }: { diff: string; maxHeight?: number }) {
  if (!diff.trim()) return <div className="rounded-[6px] border border-rule bg-sunken px-4 py-6 text-center text-[13px] text-muted">No source changes (flags only).</div>;
  const rows = parse(diff);
  const added = rows.filter((r) => r.kind === "add").length;
  const removed = rows.filter((r) => r.kind === "del").length;
  return (
    <div className="overflow-hidden rounded-[6px] border border-rule">
      <div className="flex items-center gap-3 border-b border-rule bg-surface px-3 py-1.5 font-mono text-[11px] text-muted">
        <span className="text-accent">+{added}</span>
        <span className="text-bad">−{removed}</span>
        <span>lines</span>
      </div>
      <div className="code-well overflow-auto bg-sunken" style={{ maxHeight }}>
        <table className="w-full border-collapse">
          <tbody>
            {rows.map((r, i) =>
              r.kind === "hunk" ? (
                <tr key={i} className="bg-surface/60">
                  <td colSpan={4} className="px-3 py-0.5 text-[11px] text-faint">{r.text}</td>
                </tr>
              ) : (
                <tr key={i} className={cx(r.kind === "add" && "bg-accent-soft", r.kind === "del" && "bg-bad-soft")}>
                  <td className="w-[1%] select-none whitespace-nowrap px-2 text-right text-faint">{r.old ?? ""}</td>
                  <td className="w-[1%] select-none whitespace-nowrap px-2 text-right text-faint">{r.new ?? ""}</td>
                  <td className={cx("w-[1%] select-none px-1", r.kind === "add" ? "text-accent" : r.kind === "del" ? "text-bad" : "text-faint")}>
                    {r.kind === "add" ? "+" : r.kind === "del" ? "−" : " "}
                  </td>
                  <td className="whitespace-pre pr-4">{highlightLine(r.text)}</td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
