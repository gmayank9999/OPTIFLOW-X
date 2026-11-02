"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Health, useApi } from "@/lib/api";
import { cx } from "@/lib/format";

const NAV = [
  { href: "/", label: "Overview", key: "overview" },
  { href: "/workspace/", label: "Try as User", key: "workspace" },
  { href: "/requirements/", label: "Requirements", key: "requirements" },
  { href: "/runs/", label: "Runs", key: "runs" },
  { href: "/programs/", label: "Programs", key: "programs" },
  { href: "/agents/", label: "Agents", key: "agents" },
  { href: "/experiments/", label: "Experiments", key: "experiments" },
  { href: "/predictor/", label: "Predictor", key: "predictor" },
  { href: "/security/", label: "Security", key: "security" },
  { href: "/method/", label: "Method", key: "method" },
];

function active(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  const base = href.replace(/\/$/, "");
  return pathname.startsWith(base) || (base === "/runs" && pathname.startsWith("/run")) ||
    (base === "/programs" && pathname.startsWith("/program")) ||
    (base === "/workspace" && pathname.startsWith("/workspace"));
}

export function Mark({ size = 22 }: { size?: number }) {
  // A loop arrow closing on a check: optimize, then verify.
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="0.5" y="0.5" width="23" height="23" rx="5.5" className="fill-ink" />
      <path d="M7 15.5a5.5 5.5 0 1 1 9.6 3.6" style={{ stroke: "rgb(var(--paper))" }} strokeWidth="1.8" strokeLinecap="round" />
      <path d="M14.6 19.4l2.2-.3.3-2.2" style={{ stroke: "rgb(var(--paper))" }} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9.6 11.6l1.7 1.7 3.2-3.4" style={{ stroke: "rgb(var(--accent))" }} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[216px_1fr]">
      {/* mobile top bar */}
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-rule bg-paper/95 px-4 py-3 backdrop-blur md:hidden">
        <Link href="/" className="flex items-center gap-2">
          <Mark size={20} />
          <span className="font-mono text-[12px] font-medium tracking-[0.12em]">OPTIFLOW-X</span>
        </Link>
        <div className="flex items-center gap-2">
          <Link
            href="/workspace/"
            className="flex items-center gap-1.5 rounded-[5px] border border-accent/40 bg-accent-soft px-2.5 py-1 text-[11px] font-semibold text-accent hover:bg-accent hover:text-white"
          >
            <span>🚀</span>
            <span>Try as User</span>
          </Link>
          <button onClick={() => setOpen((o) => !o)} className="rounded border border-rule px-2.5 py-1 text-[12px]" aria-expanded={open}>
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      <aside
        className={cx(
          "z-20 border-r border-rule bg-paper md:sticky md:top-0 md:flex md:h-screen md:flex-col",
          open ? "block border-b px-3 pb-4" : "hidden",
        )}
      >
        <Link href="/" className="hidden items-center gap-2.5 px-5 pb-5 pt-6 md:flex">
          <Mark />
          <div className="leading-tight">
            <div className="font-mono text-[12.5px] font-medium tracking-[0.14em]">OPTIFLOW-X</div>
            <div className="text-[11px] text-muted">verified C/C++ optimization</div>
          </div>
        </Link>

        {/* Prominent Try as User Callout */}
        <div className="px-3 pb-3 hidden md:block">
          <Link
            href="/workspace/"
            className={cx(
              "flex items-center justify-between rounded-[6px] px-3 py-2 text-[12px] font-semibold transition-all",
              pathname.startsWith("/workspace")
                ? "bg-ink text-paper shadow-sm"
                : "border border-accent/50 bg-accent-soft text-accent hover:border-accent hover:bg-accent hover:text-white",
            )}
          >
            <span className="flex items-center gap-2">
              <span className="text-[14px]">🚀</span>
              <span>Try as User</span>
            </span>
            <span className={cx(
              "rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider",
              pathname.startsWith("/workspace") ? "bg-white/20 text-paper" : "bg-accent/15 text-accent"
            )}>
              Guided
            </span>
          </Link>
        </div>
        <nav className="flex flex-col gap-0.5 px-3 pt-2 md:pt-0">
          {NAV.map((item, i) => {
            const on = active(pathname, item.href);
            return (
              <Link
                key={item.key}
                href={item.href}
                className={cx(
                  "group flex items-center gap-3 rounded-[5px] px-2.5 py-[7px] transition-colors",
                  on ? "bg-surface text-ink shadow-[0_0_0_1px_rgb(var(--rule))]" : "text-muted hover:text-ink",
                )}
              >
                <span className={cx("font-mono text-[10.5px]", on ? "text-accent" : "text-faint")}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto hidden md:block">
          <SystemStatus />
        </div>
      </aside>

      <main className="min-w-0 px-4 pb-16 pt-5 md:px-10 md:pt-9">
        <div className="mx-auto max-w-[1240px]">{children}</div>
      </main>
    </div>
  );
}

function Dot({ ok, label, title }: { ok: boolean | null; label: string; title?: string }) {
  return (
    <div className="flex items-center justify-between py-[3px]" title={title}>
      <span className="text-muted">{label}</span>
      <span className="flex items-center gap-1.5">
        <span
          className={cx("inline-block h-[7px] w-[7px] rounded-full", ok === null ? "bg-faint" : ok ? "bg-accent" : "bg-bad")}
        />
        <span className="font-mono text-[11px]">{ok === null ? "…" : ok ? "ok" : "off"}</span>
      </span>
    </div>
  );
}

function SystemStatus() {
  const { data } = useApi<Health>("/health", 8000);
  const anyKey = data ? Object.values(data.keys).some(Boolean) : null;
  return (
    <div className="border-t border-rule px-5 py-4 text-[12px]">
      <div className="eyebrow mb-2">System</div>
      <Dot ok={data ? data.docker : null} label="Docker" />
      <Dot ok={data ? data.sandbox_image : null} label="Sandbox image" />
      <Dot ok={anyKey} label="LLM key" title={data ? Object.entries(data.keys).filter(([, v]) => v).map(([k]) => k).join(", ") : ""} />
      <div className="flex items-center justify-between py-[3px]">
        <span className="text-muted">Queue</span>
        <span className="font-mono text-[11px]">
          {data?.active_run ? (
            <span className="flex items-center gap-1.5 text-accent">
              <span className="live-dot inline-block h-[7px] w-[7px] rounded-full bg-accent" />
              running{data.queue_depth ? ` +${data.queue_depth}` : ""}
            </span>
          ) : (
            "idle"
          )}
        </span>
      </div>
      <ThemeToggle />
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<string>("system");
  useEffect(() => {
    try {
      setTheme(localStorage.getItem("optiflow-theme") || "system");
    } catch {}
  }, []);
  const apply = (t: string) => {
    setTheme(t);
    try {
      if (t === "system") {
        localStorage.removeItem("optiflow-theme");
        delete document.documentElement.dataset.theme;
      } else {
        localStorage.setItem("optiflow-theme", t);
        document.documentElement.dataset.theme = t;
      }
    } catch {}
  };
  return (
    <div className="mt-3 grid grid-cols-3 rounded-[5px] border border-rule p-0.5 text-[11px]">
      {["light", "system", "dark"].map((t) => (
        <button
          key={t}
          onClick={() => apply(t)}
          className={cx("rounded-[4px] py-[3px] capitalize", theme === t ? "bg-surface text-ink shadow-[0_0_0_1px_rgb(var(--rule))]" : "text-muted")}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
