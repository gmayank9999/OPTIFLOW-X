"use client";

import { useApi } from "@/lib/api";
import { cx, fmtMs, fmtPct } from "@/lib/format";
import { Empty, ErrorNote, KV, PageHeader, Panel, Skeleton, Stat, StatRow } from "@/components/ui";

type Stability = {
  stability: null | { runs: number; sessions: number; programs: Record<string, { median_ms: number; cv_within_max: number; cv_across_sessions: number }> };
  machine: Record<string, string> | null;
};

const PROTOCOL: [string, string][] = [
  ["Sandbox", "Docker, no network, non-root, all capabilities dropped (CAP_PERFMON only for profiling the trusted baseline), read-only root, memory and PID limits, hard timeout, pinned CPU."],
  ["Correctness", "Exit status and output on 3 inputs (incl. n=1 and odd sizes like 33), exact or tolerance compare; then an AddressSanitizer + UBSan build on the small inputs. Any failure rejects."],
  ["Timing", "hrtime harness (CLOCK_MONOTONIC, ns resolution; CPU time and peak RSS from wait4). Binaries and input staged in tmpfs. Baseline and candidate interleaved round by round in one container; 2 warm-ups, 10–30 timed runs depending on runtime."],
  ["Acceptance", "Median speedup ≥ 1.05× and one-sided Mann-Whitney U p < 0.05, and better than the current best. Decided by rules, never by the LLM."],
  ["Stopping", "Attempt budget, per-run USD cap, two accepted attempts in a row gaining < 3%, or three rejections in a row."],
  ["Flags", "Whitelisted. -Ofast / -ffast-math only for tolerance-compared programs; dropped flags are reported back to the Strategist."],
];

export default function MethodPage() {
  const { data, error } = useApi<Stability>("/stability");
  const progs = Object.entries(data?.stability?.programs ?? {});
  const under3 = progs.filter(([, p]) => p.cv_within_max < 0.03).length;
  const under5 = progs.filter(([, p]) => p.cv_within_max < 0.05).length;
  const inWindow = progs.filter(([, p]) => p.median_ms >= 300 && p.median_ms <= 5000).length;
  const maxCv = Math.max(0.1, ...progs.map(([, p]) => p.cv_within_max));

  return (
    <>
      <PageHeader eyebrow="Method" title="How the numbers are produced">
        Everything else in this dashboard is only as trustworthy as the measurements underneath it. This page shows the
        protocol, the machine, and the stability test that checks timing noise per program.
      </PageHeader>
      {error && <ErrorNote error={error} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Panel eyebrow="Protocol" title="Verification and measurement">
          <dl className="flex flex-col">
            {PROTOCOL.map(([k, v]) => (
              <div key={k} className="grid grid-cols-1 gap-1 border-b border-rule py-2.5 last:border-b-0 sm:grid-cols-[110px_1fr] sm:gap-4">
                <dt className="font-medium">{k}</dt>
                <dd className="text-[13px] text-muted">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <Panel eyebrow="Machine" title="Where it was measured">
          {data?.machine ? (
            <>
              <KV k="CPU" v={data.machine.cpu} mono={false} />
              <KV k="Cores visible" v={data.machine.cores_visible} />
              <KV k="Memory" v={data.machine.mem} />
              <KV k="Kernel" v={data.machine.kernel} />
              <KV k="GCC" v={data.machine.gcc?.replace(/^gcc\s*/, "")} />
              <KV k="Clang" v={data.machine.clang?.replace(/^Ubuntu clang version\s*/, "")} />
              <KV k="Host" v={data.machine.host_os} mono={false} />
              <p className="mt-3 text-[12px] text-muted">
                A laptop under Docker Desktop/WSL2 is a noisy place to time code: other processes share the core the sandbox is pinned to.
                Interleaved measurement and the significance test are what keep that noise from turning into false speedups.
              </p>
            </>
          ) : <Skeleton className="h-40" />}
        </Panel>
      </div>

      <div className="mt-8">
        <div className="eyebrow mb-3">Stability test · baseline at -O2, {data?.stability?.runs ?? "—"} runs × {data?.stability?.sessions ?? "—"} sessions per program</div>
        {!data ? <Skeleton className="h-60" /> : !progs.length ? (
          <Empty title="No stability data">Run <span className="font-mono">python -m optiflow.experiments.stability</span>.</Empty>
        ) : (
          <>
            <StatRow>
              <Stat label="Programs" value={progs.length} />
              <Stat label="CV < 3%" value={`${under3}/${progs.length}`} tone={under3 / progs.length > 0.8 ? "accent" : "warn"} sub="plan target: all" />
              <Stat label="CV < 5%" value={`${under5}/${progs.length}`} />
              <Stat label="Runtime 0.3–5 s" value={`${inWindow}/${progs.length}`} />
              <Stat label="Median runtime" value={fmtMs(median(progs.map(([, p]) => p.median_ms)))} />
            </StatRow>
            <Panel className="mt-4" pad={false}>
              <div className="grid grid-cols-1 gap-x-8 p-4 md:grid-cols-2">
                {progs.sort((a, b) => b[1].cv_within_max - a[1].cv_within_max).map(([pid, p]) => (
                  <div key={pid} className="grid grid-cols-[150px_1fr_86px] items-center gap-3 border-b border-rule py-[5px] text-[12px] last:border-b-0">
                    <span className="truncate font-mono text-muted">{pid}</span>
                    <div className="relative h-[8px] rounded-full bg-sunken">
                      <div className="absolute inset-y-0 border-l border-dashed border-accent" style={{ left: `${(0.03 / maxCv) * 100}%` }} />
                      <div className="absolute inset-y-0 border-l border-dashed border-warn" style={{ left: `${(0.05 / maxCv) * 100}%` }} />
                      <div className={cx("bar-grow h-full rounded-full", p.cv_within_max < 0.03 ? "bg-accent" : p.cv_within_max < 0.05 ? "bg-faint" : "bg-warn")} style={{ width: `${Math.min(1, p.cv_within_max / maxCv) * 100}%` }} />
                    </div>
                    <span className="num text-right">{fmtPct(p.cv_within_max)} <span className="text-faint">{fmtMs(p.median_ms)}</span></span>
                  </div>
                ))}
              </div>
              <div className="border-t border-rule px-4 py-2 text-[11.5px] text-faint">Bar: worst within-session CV. Dashed: 3% (target) and 5% (re-run threshold).</div>
            </Panel>
          </>
        )}
      </div>
    </>
  );
}

function median(v: number[]): number | null {
  if (!v.length) return null;
  const s = [...v].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
}
