"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { cx, REASON_LABEL } from "@/lib/format";

export function PageHeader({ eyebrow, title, children, actions }: { eyebrow?: string; title: ReactNode; children?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-col gap-4 border-b border-rule pb-6 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-2">{eyebrow}</div>}
        <h1 className="text-[26px] font-semibold leading-[1.15] tracking-[-0.015em] md:text-[30px]">{title}</h1>
        {children && <div className="mt-2 max-w-[720px] text-[14px] text-muted">{children}</div>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({ title, eyebrow, right, children, className, pad = true }: {
  title?: ReactNode; eyebrow?: string; right?: ReactNode; children: ReactNode; className?: string; pad?: boolean;
}) {
  return (
    <section className={cx("rounded-[7px] border border-rule bg-surface", className)}>
      {(title || eyebrow || right) && (
        <div className="flex items-center justify-between gap-3 border-b border-rule px-4 py-3">
          <div className="min-w-0">
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <div className="truncate text-[13.5px] font-semibold">{title}</div>}
          </div>
          {right}
        </div>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "accent" | "warn" | "bad" }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow mb-1.5">{label}</div>
      <div className={cx("num text-[26px] font-medium leading-none tracking-[-0.02em]", tone === "accent" && "text-accent", tone === "warn" && "text-warn", tone === "bad" && "text-bad")}>
        {value}
      </div>
      {sub && <div className="mt-1.5 text-[12px] text-muted">{sub}</div>}
    </div>
  );
}

export function StatRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-x-6 gap-y-6 rounded-[7px] border border-rule bg-surface px-5 py-5 md:grid-cols-5">{children}</div>;
}

type Tone = "neutral" | "accent" | "warn" | "bad" | "info" | "outline";

export function Pill({ children, tone = "neutral", className, title }: { children: ReactNode; tone?: Tone; className?: string; title?: string }) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-[4px] px-1.5 py-[1px] font-mono text-[11px] leading-[17px]",
        tone === "neutral" && "bg-sunken text-muted",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "warn" && "bg-warn-soft text-warn",
        tone === "bad" && "bg-bad-soft text-bad",
        tone === "info" && "bg-sunken text-info",
        tone === "outline" && "border border-rule text-muted",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function VerdictPill({ reason, accepted }: { reason: string; accepted: boolean }) {
  return <Pill tone={accepted ? "accent" : reason === "no_significant_gain" || reason === "no_improvement" ? "warn" : "bad"}>{accepted ? "accepted" : REASON_LABEL[reason] ?? reason}</Pill>;
}

export function StatusPill({ status }: { status: string }) {
  if (status === "running")
    return (
      <Pill tone="accent">
        <span className="live-dot inline-block h-[6px] w-[6px] rounded-full bg-accent" />
        running
      </Pill>
    );
  if (status === "queued") return <Pill tone="outline">queued</Pill>;
  if (status === "failed") return <Pill tone="bad">failed</Pill>;
  return <Pill>done</Pill>;
}

export function Segmented<T extends string>({ value, options, onChange, size = "md" }: {
  value: T; options: { value: T; label: string; hint?: string }[]; onChange: (v: T) => void; size?: "sm" | "md";
}) {
  return (
    <div className="inline-flex flex-wrap rounded-[6px] border border-rule bg-sunken p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.hint}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-[4px] transition-colors",
            size === "sm" ? "px-2 py-[2px] text-[11.5px]" : "px-2.5 py-[5px] text-[12.5px]",
            value === o.value ? "bg-surface font-medium text-ink shadow-[0_0_0_1px_rgb(var(--rule))]" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Button({ children, onClick, href, variant = "primary", disabled, type = "button" }: {
  children: ReactNode; onClick?: () => void; href?: string; variant?: "primary" | "ghost"; disabled?: boolean; type?: "button" | "submit";
}) {
  const cls = cx(
    "inline-flex items-center justify-center gap-2 rounded-[6px] px-3.5 py-[7px] text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
    variant === "primary" ? "bg-ink text-paper hover:bg-ink/85" : "border border-rule bg-surface text-ink hover:bg-sunken",
  );
  if (href) return <Link href={href} className={cls}>{children}</Link>;
  return <button type={type} onClick={onClick} disabled={disabled} className={cls}>{children}</button>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-[7px] border border-dashed border-rule px-6 py-10 text-center">
      <div className="font-medium">{title}</div>
      {children && <div className="mx-auto mt-1.5 max-w-[520px] text-[13px] text-muted">{children}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded bg-sunken", className)} />;
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <div className="rounded-[7px] border border-bad/30 bg-bad-soft px-4 py-3 text-[13px] text-bad">
      Couldn&apos;t reach the API: <span className="font-mono">{error}</span>. Start it with{" "}
      <span className="font-mono">uvicorn optiflow.api.main:app --port 8000</span>.
    </div>
  );
}

export function Th({ children, right, className }: { children?: ReactNode; right?: boolean; className?: string }) {
  return <th className={cx("whitespace-nowrap border-b border-rule bg-sunken/60 px-3 py-2 font-mono text-[10.5px] font-normal uppercase tracking-[0.06em] text-muted", right ? "text-right" : "text-left", className)}>{children}</th>;
}

export function Td({ children, right, mono, className, title }: { children?: ReactNode; right?: boolean; mono?: boolean; className?: string; title?: string }) {
  return <td title={title} className={cx("border-b border-rule px-3 py-2 align-middle", right && "text-right", mono && "num", className)}>{children}</td>;
}

export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-[7px] border border-rule bg-surface">
      <table className="w-full border-collapse text-[13px] [&_tr:last-child_td]:border-b-0">{children}</table>
    </div>
  );
}

export function KV({ k, v, mono = true }: { k: ReactNode; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule py-[7px] last:border-b-0">
      <span className="text-muted">{k}</span>
      <span className={cx("text-right", mono && "num")}>{v}</span>
    </div>
  );
}

export function SpeedupBar({ value, max, tone = "accent" }: { value: number | null; max: number; tone?: "accent" | "muted" }) {
  // Log-scaled bar: 1x = empty, max = full. Speedups compound, so the
  // eye should compare ratios, not differences.
  const v = value && value > 0 ? value : 0;
  const frac = v <= 1 || max <= 1 ? 0 : Math.min(1, Math.log(v) / Math.log(max));
  return (
    <div className="h-[6px] w-full overflow-hidden rounded-full bg-sunken">
      <div className={cx("bar-grow h-full rounded-full", tone === "accent" ? "bg-accent" : "bg-faint")} style={{ width: `${frac * 100}%` }} />
    </div>
  );
}
