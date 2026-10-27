"use client";

import Link from "next/link";
import { ProgramRow } from "@/lib/api";
import { cx, fmtSpeedup, num } from "@/lib/format";

/**
 * Per-program comparison on a log axis: flags-only (-O3 -march=native)
 * as a grey tick-bar, the best agent run as the accent bar. Sorted by the
 * agent's speedup so the shape of the distribution reads at a glance.
 */
export function SpeedupChart({ programs, limit }: { programs: ProgramRow[]; limit?: number }) {
  const rows = programs
    .map((p) => ({ ...p, best: num(p.best_speedup), flags: num(p.flags_speedup) }))
    .filter((p) => p.best !== null || p.flags !== null)
    .sort((a, b) => (b.best ?? b.flags ?? 0) - (a.best ?? a.flags ?? 0))
    .slice(0, limit);
  if (!rows.length) return null;
  const max = Math.max(2, ...rows.map((r) => Math.max(r.best ?? 0, r.flags ?? 0)));
  const scale = (v: number | null) => (v && v > 0 ? Math.max(0, Math.log(v) / Math.log(max)) : 0);
  const below = (v: number | null) => (v !== null && v < 1 ? Math.min(1, Math.log(1 / v) / Math.log(max)) : 0);
  const gridValues = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].filter((g) => g <= max);

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-4 text-[11.5px] text-muted">
        <span className="flex items-center gap-1.5"><span className="inline-block h-[6px] w-4 rounded-full bg-accent" />best agent run</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-[6px] w-4 rounded-full bg-faint" />-O3 -march=native</span>
        <span className="ml-auto font-mono text-[10.5px]">log scale · speedup vs -O2</span>
      </div>
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-[170px] right-[64px] hidden sm:block">
          {gridValues.map((g) => (
            <div key={g} className="absolute inset-y-0 border-l border-rule/70" style={{ left: `${scale(g) * 100}%` }}>
              <span className="absolute -top-4 -translate-x-1/2 font-mono text-[9.5px] text-faint">{g}×</span>
            </div>
          ))}
        </div>
        <div className="pt-4">
          {rows.map((r) => (
            <Link key={r.id} href={`/program/?id=${r.id}`} className="group grid grid-cols-[120px_1fr_56px] items-center gap-3 py-[3px] sm:grid-cols-[158px_1fr_56px]">
              <span className="truncate font-mono text-[11.5px] text-muted group-hover:text-ink">{r.id}</span>
              <span className="relative flex h-[14px] flex-col justify-center gap-[2px]">
                <span className={cx("bar-grow block h-[5px] rounded-full", r.best !== null && r.best < 1 ? "bg-bad/60" : "bg-accent")} style={{ width: `${(r.best !== null && r.best >= 1 ? scale(r.best) : below(r.best)) * 100}%` }} />
                <span className="bar-grow block h-[3px] rounded-full bg-faint" style={{ width: `${scale(r.flags) * 100}%` }} />
              </span>
              <span className="num text-right text-[12px]">{fmtSpeedup(r.best ?? r.flags)}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
