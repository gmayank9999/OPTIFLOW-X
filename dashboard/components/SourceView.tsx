"use client";

import { Hotspot, Loop } from "@/lib/api";
import { highlightLine } from "@/lib/highlight";
import { cx } from "@/lib/format";

/**
 * Source with a heat gutter: each line in a profiled hotspot gets a bar
 * whose intensity is that loop's share of perf samples. The tightest
 * hottest loop is tinted, so "where does the time go" is visible at a
 * glance, before reading any numbers.
 */
export function SourceView({ source, hotspots = [], loops = [], maxHeight = 560 }: {
  source: string; hotspots?: Hotspot[]; loops?: Loop[]; maxHeight?: number;
}) {
  const lines = source.replace(/\n$/, "").split("\n");
  const heat = new Array(lines.length + 1).fill(0);
  for (const h of hotspots) {
    for (let l = h.start_line; l <= h.end_line && l <= lines.length; l++) heat[l] = Math.max(heat[l], h.time_pct);
  }
  const top = hotspots[0];
  const loopStarts = new Map(loops.map((l) => [l.line, l]));

  return (
    <div className="code-well overflow-auto rounded-[6px] border border-rule bg-sunken" style={{ maxHeight }}>
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((text, i) => {
            const n = i + 1;
            const h = heat[n];
            const inTop = top && n >= top.start_line && n <= top.end_line;
            const loop = loopStarts.get(n);
            return (
              <tr key={n} className={cx(inTop && "bg-accent-soft/70")}>
                <td className="w-[5px] p-0">
                  <div className="h-[19px] w-[4px]" style={{ background: h ? `rgb(var(--accent) / ${0.15 + 0.85 * (h / 100)})` : "transparent" }} title={h ? `${h.toFixed(1)}% of samples` : undefined} />
                </td>
                <td className="select-none whitespace-nowrap px-3 text-right align-top text-faint">{n}</td>
                <td className="whitespace-pre pr-4 align-top">
                  {highlightLine(text)}
                  {loop && (
                    <span className="ml-3 select-none font-sans text-[10.5px] text-faint">
                      loop d{loop.depth}{loop.iter_vars.length ? ` · ${loop.iter_vars.join(",")}` : ""}
                    </span>
                  )}
                  {top && n === top.start_line && (
                    <span className="ml-2 select-none rounded-[3px] bg-accent px-1 py-[1px] font-sans text-[10px] font-medium text-paper">
                      {top.time_pct.toFixed(0)}% of time
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
