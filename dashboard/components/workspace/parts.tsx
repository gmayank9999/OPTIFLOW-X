"use client";

import { ReactNode, useId, useState } from "react";
import { cx } from "@/lib/format";

/** A selectable card backed by a real radio input, so keyboard and screen
 *  readers get native behaviour; the card shows the selected state. */
export function RadioCard({
  name, checked, onChange, title, desc, icon, disabled, badge,
}: {
  name: string; checked: boolean; onChange: () => void; title: string; desc?: ReactNode; icon?: ReactNode; disabled?: boolean; badge?: ReactNode;
}) {
  return (
    <label
      className={cx(
        "group relative flex cursor-pointer gap-3 rounded-[10px] border-2 p-4 transition-colors focus-within:ring-2 focus-within:ring-accent/40",
        checked ? "border-accent bg-accent-soft" : "border-rule bg-surface hover:border-ink/30",
        disabled && "cursor-not-allowed opacity-55 hover:border-rule",
      )}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} disabled={disabled} className="sr-only" />
      {icon && <span className="mt-0.5 text-[22px] leading-none" aria-hidden>{icon}</span>}
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2 text-[15px] font-semibold text-ink">{title}{badge}</span>
        {desc && <span className="mt-1 block text-[13.5px] leading-snug text-muted">{desc}</span>}
      </span>
      <span
        aria-hidden
        className={cx("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-bold", checked ? "border-accent bg-accent text-paper" : "border-rule text-transparent")}
      >
        ✓
      </span>
    </label>
  );
}

export const STEPS = ["Choose code", "Choose goal", "Review", "Optimize", "Compare"] as const;

export function Stepper({ current, reachable, onGo }: { current: number; reachable: (step: number) => boolean; onGo: (step: number) => void }) {
  return (
    <nav aria-label="Progress">
      <ol className="flex items-center gap-1.5 overflow-x-auto pb-1">
        {STEPS.map((label, i) => {
          const n = i + 1;
          const done = n < current;
          const active = n === current;
          const can = reachable(n) && !active;
          return (
            <li key={label} className="flex min-w-0 flex-1 items-center gap-1.5">
              <button
                type="button"
                disabled={!can}
                onClick={() => onGo(n)}
                aria-current={active ? "step" : undefined}
                className={cx(
                  "flex w-full min-w-[64px] items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left transition-colors",
                  active ? "bg-ink text-paper" : done ? "bg-accent-soft text-ink hover:bg-accent-soft/70" : "bg-sunken text-muted",
                  !can && !active && "cursor-default",
                )}
              >
                <span
                  className={cx(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[12px] font-bold",
                    active ? "bg-paper text-ink" : done ? "bg-accent text-paper" : "bg-rule text-muted",
                  )}
                >
                  {done ? "✓" : n}
                </span>
                <span className="hidden truncate text-[13px] font-medium sm:block">{label}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-[12.5px] text-muted sm:hidden">Step {current} of {STEPS.length}: {STEPS[current - 1]}</p>
    </nav>
  );
}

export function Accordion({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="rounded-[10px] border border-rule bg-surface">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-3 rounded-[10px] px-4 py-3.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <span>
          <span className="block text-[14.5px] font-semibold text-ink">{title}</span>
          {hint && <span className="block text-[12.5px] text-muted">{hint}</span>}
        </span>
        <span aria-hidden className={cx("text-muted transition-transform", open && "rotate-180")}>▾</span>
      </button>
      {open && <div id={id} className="space-y-5 border-t border-rule px-4 py-4">{children}</div>}
    </div>
  );
}

export function Notice({ tone, title, children }: { tone: "bad" | "warn" | "info" | "good"; title?: string; children: ReactNode }) {
  const cls = {
    bad: "border-bad/30 bg-bad-soft text-bad",
    warn: "border-warn/30 bg-warn-soft text-ink",
    info: "border-rule bg-sunken text-ink",
    good: "border-accent/30 bg-accent-soft text-ink",
  }[tone];
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={cx("rounded-[10px] border px-4 py-3 text-[14px] leading-snug", cls)}>
      {title && <div className="mb-0.5 font-semibold">{title}</div>}
      <div className="whitespace-pre-wrap">{children}</div>
    </div>
  );
}

export function BigButton({ children, onClick, disabled, variant = "primary" }: { children: ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "ghost" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-[10px] px-5 py-3 text-[15px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" ? "bg-ink text-paper hover:bg-ink/85" : "border border-rule bg-surface text-ink hover:bg-sunken",
      )}
    >
      {children}
    </button>
  );
}
