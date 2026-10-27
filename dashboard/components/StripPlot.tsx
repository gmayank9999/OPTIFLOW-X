"use client";

import { BenchResult } from "@/lib/api";
import { fmtMs } from "@/lib/format";

/**
 * Every timed run of baseline and candidate as a dot on one shared axis,
 * with the medians marked. The Critic's accept/reject is a statement about
 * these two distributions; showing the raw samples (not just two medians)
 * makes it obvious when a "speedup" is really noise.
 */
export function StripPlot({ baseline, candidate, height = 74 }: { baseline: BenchResult; candidate: BenchResult; height?: number }) {
  const all = [...baseline.runtimes_ms, ...candidate.runtimes_ms];
  if (!all.length) return null;
  const lo = Math.min(...all) * 0.92;
  const hi = Math.max(...all) * 1.04;
  const W = 520;
  const pad = 74;
  const sx = (v: number) => pad + ((v - lo) / (hi - lo || 1)) * (W - pad - 10);
  const rows = [
    { label: "baseline", data: baseline, y: 22, color: "rgb(var(--faint))" },
    { label: "candidate", data: candidate, y: 50, color: "rgb(var(--accent))" },
  ];
  const jitter = (i: number) => ((i * 37) % 9) - 4;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-label="timing samples">
      {rows.map((r) => (
        <g key={r.label}>
          <text x={0} y={r.y + 4} className="fill-muted font-mono" fontSize={10.5}>{r.label}</text>
          <line x1={pad} x2={W - 10} y1={r.y} y2={r.y} style={{ stroke: "rgb(var(--rule))" }} />
          {r.data.runtimes_ms.map((v, i) => (
            <circle key={i} cx={sx(v)} cy={r.y + jitter(i)} r={2.6} style={{ fill: r.color, fillOpacity: 0.75 }} />
          ))}
          <line x1={sx(r.data.median_ms)} x2={sx(r.data.median_ms)} y1={r.y - 9} y2={r.y + 9} style={{ stroke: "rgb(var(--ink))", strokeWidth: 1.5 }} />
        </g>
      ))}
      <text x={pad} y={height - 2} className="fill-faint font-mono" fontSize={9.5}>{fmtMs(lo)}</text>
      <text x={W - 10} y={height - 2} textAnchor="end" className="fill-faint font-mono" fontSize={9.5}>{fmtMs(hi)}</text>
    </svg>
  );
}
