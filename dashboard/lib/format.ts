export const AGENTS = ["analyzer", "profiler", "manager", "strategist", "transformer", "compiler_exec", "benchmark", "critic"] as const;

export const AGENT_LABEL: Record<string, string> = {
  analyzer: "Analyzer",
  profiler: "Profiler",
  manager: "Manager",
  strategist: "Strategist",
  transformer: "Transformer",
  compiler_exec: "Compile & test",
  benchmark: "Benchmark",
  critic: "Critic",
};

export const laneColor = (agent: string, alpha = 1) => `rgb(var(--lane-${agent}, var(--muted)) / ${alpha})`;

export function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function fmtSpeedup(v: unknown, digits = 2): string {
  const n = num(v);
  return n === null ? "—" : `${n.toFixed(digits)}×`;
}

export function fmtMs(v: unknown): string {
  const n = num(v);
  if (n === null) return "—";
  if (n >= 10_000) return `${(n / 1000).toFixed(1)} s`;
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`;
  if (n >= 100) return `${n.toFixed(0)} ms`;
  if (n >= 10) return `${n.toFixed(1)} ms`;
  return `${n.toFixed(2)} ms`;
}

export function fmtPct(v: unknown, digits = 1): string {
  const n = num(v);
  return n === null ? "—" : `${(n * 100).toFixed(digits)}%`;
}

export function fmtUsd(v: unknown): string {
  const n = num(v);
  if (n === null) return "—";
  if (n === 0) return "$0";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(3)}`;
}

export function fmtInt(v: unknown): string {
  const n = num(v);
  return n === null ? "—" : Math.round(n).toLocaleString("en-US");
}

export function fmtTokens(v: unknown): string {
  const n = num(v);
  if (n === null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return Math.round(n).toLocaleString("en-US");
}

export function fmtAgo(ts: unknown): string {
  const n = num(ts);
  if (!n) return "—";
  const s = Date.now() / 1000 - n;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(n * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function geomean(values: (number | null | undefined)[]): number | null {
  const v = values.filter((x): x is number => typeof x === "number" && x > 0);
  if (!v.length) return null;
  return Math.exp(v.reduce((a, b) => a + Math.log(b), 0) / v.length);
}

export const REASON_LABEL: Record<string, string> = {
  accepted: "Accepted",
  compile_error: "Compile error",
  wrong_output: "Wrong output",
  sanitizer_error: "Sanitizer",
  no_significant_gain: "No significant gain",
  no_improvement: "Not better than best",
  no_change: "Identical to best",
  plan_error: "Unparseable plan",
  unsafe_candidate: "Unsafe source",
  empty_output: "Empty rewrite",
  no_measurement: "No measurement",
  toolerror: "Tool error",
  missingcontext: "Missing context",
};

export const STOP_LABEL: Record<string, string> = {
  attempt_budget: "attempt budget used",
  cost_cap: "cost cap reached",
  diminishing_returns: "diminishing returns",
  consecutive_rejects: "3 rejects in a row",
  manager_stop: "manager stopped",
  no_more_strategies: "nothing left to try",
  completed: "completed",
  error: "error",
};

export const CATEGORY_LABEL: Record<string, string> = {
  matrix: "Matrix",
  stencil: "Stencil / numerical",
  sorting: "Sorting / search",
  graph: "Graph",
  dp: "Dynamic programming",
  string: "String",
  data_layout: "Data layout",
};

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
