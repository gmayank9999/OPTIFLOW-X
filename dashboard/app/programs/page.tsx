"use client";

import Link from "next/link";
import { useState } from "react";
import { ProgramRow, useApi } from "@/lib/api";
import { CATEGORY_LABEL, cx, fmtMs, fmtPct, fmtSpeedup, num } from "@/lib/format";
import { ErrorNote, PageHeader, Pill, Segmented, Skeleton, SpeedupBar, TableWrap, Td, Th } from "@/components/ui";

export default function ProgramsPage() {
  const { data, error } = useApi<ProgramRow[]>("/programs", 15000);
  const [cat, setCat] = useState("all");
  const [q, setQ] = useState("");
  const cats = ["all", ...Array.from(new Set((data ?? []).map((p) => p.category)))];
  const rows = (data ?? []).filter((p) => (cat === "all" || p.category === cat) && (!q || p.id.includes(q)));
  const max = Math.max(2, ...rows.map((r) => Math.max(num(r.best_speedup) ?? 0, num(r.flags_speedup) ?? 0)));

  return (
    <>
      <PageHeader eyebrow="Benchmark suite" title="50 deliberately unoptimized programs">
        Each is correct, deterministic and reads stdin; each has three inputs (including an n=1 edge case and an odd size like 33)
        with reference outputs generated at -O0. The grey bar is -O3 -march=native alone; the green bar is the best verified agent run.
      </PageHeader>
      {error && <div className="mb-4"><ErrorNote error={error} /></div>}
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Segmented size="sm" value={cat} onChange={setCat} options={cats.map((c) => ({ value: c, label: c === "all" ? "All" : CATEGORY_LABEL[c] ?? c }))} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search programs…" className="w-full rounded-[6px] border border-rule bg-surface px-3 py-[6px] text-[13px] outline-none focus:border-ink/40 lg:w-64" />
      </div>
      {!data ? (
        <div className="space-y-2">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-10" />)}</div>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>Program</Th><Th>Category</Th><Th right>Baseline</Th><Th right>CV</Th><Th right>-O3</Th>
              <Th right>Best agent</Th><Th className="w-[22%]">Speedup (log)</Th><Th>Winning change</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const cv = num(p.cv);
              return (
                <tr key={p.id} className="hover:bg-sunken/50">
                  <Td>
                    <Link href={`/program/?id=${p.id}`} className="font-mono text-[12.5px] hover:underline">{p.id}</Link>
                    {p.subset10 && <span className="ml-2 font-mono text-[10px] text-faint" title="part of the 10-program experiment subset">S10</span>}
                  </Td>
                  <Td className="text-[12px] text-muted">{CATEGORY_LABEL[p.category] ?? p.category}</Td>
                  <Td right mono>{fmtMs(p.baseline_ms)}</Td>
                  <Td right mono className={cx(cv !== null && cv > 0.05 ? "text-warn" : cv !== null && cv <= 0.03 ? "text-accent" : "text-muted")}>{fmtPct(cv)}</Td>
                  <Td right mono className="text-muted">{fmtSpeedup(p.flags_speedup)}</Td>
                  <Td right mono className={cx(num(p.best_speedup) && num(p.best_speedup)! >= 1.05 ? "font-medium text-accent" : "text-muted")}>{fmtSpeedup(p.best_speedup)}</Td>
                  <Td>
                    <div className="flex flex-col gap-[3px]">
                      <SpeedupBar value={num(p.best_speedup)} max={max} />
                      <SpeedupBar value={num(p.flags_speedup)} max={max} tone="muted" />
                    </div>
                  </Td>
                  <Td>{p.best_strategy ? <Pill>{p.best_strategy}</Pill> : <span className="text-faint">—</span>}</Td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
    </>
  );
}
