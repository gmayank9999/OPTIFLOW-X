"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// In production the dashboard is served by the FastAPI app itself (same
// origin). In `next dev` (port 3000) it talks to the API on :8000.
export function apiOrigin(): string {
  if (process.env.NEXT_PUBLIC_API_ORIGIN) return process.env.NEXT_PUBLIC_API_ORIGIN;
  if (typeof window === "undefined") return "";
  return window.location.port === "3000" ? "http://localhost:8000" : window.location.origin;
}

const TOKEN_KEY = "optiflow-api-token";

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token: string) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail: any) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${apiOrigin()}/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail: any = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    const message = typeof detail === "string" ? detail : detail?.message ?? JSON.stringify(detail);
    throw new ApiError(res.status, `${res.status} ${message}`, detail);
  }
  return res.json() as Promise<T>;
}

export function useApi<T>(path: string | null, refreshMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const alive = useRef(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      const result = await api<T>(path);
      if (alive.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    alive.current = true;
    setLoading(!!path);
    load();
    if (!refreshMs) return () => void (alive.current = false);
    const id = setInterval(load, refreshMs);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [load, path, refreshMs]);

  return { data, error, loading, reload: load };
}

export function streamUrl(runId: string): string {
  const origin = apiOrigin().replace(/^http/, "ws");
  return `${origin}/api/runs/${runId}/stream`;
}

/* ----------------------------------------------------------------- types */

export type Health = {
  docker: boolean;
  sandbox_image: boolean;
  sandbox?: { backend: "docker" | "local"; ready: boolean; isolation: string; tools?: Record<string, boolean> };
  keys: Record<string, boolean>;
  model_assignment: string;
  assignments: Record<string, Record<string, string>>;
  machine: Record<string, string> | null;
  queue_depth: number;
  active_run: string | null;
  write_requires_token?: boolean;
  a2a_reviewer?: string;
};

export type GuardrailFinding = { kind: string; rule: string; excerpt: string };
export type GuardrailCheck = { ok: boolean; surface: string; findings: GuardrailFinding[] };
export type GuardrailEvent = { run_id: string; program_id: string; agent: string; attempt: number | null; stage: string; detail: string; t?: number };

export type ProgramRow = {
  id: string;
  category: string;
  language: string;
  compare: string;
  subset10: boolean;
  baseline_ms: number | null;
  cv: number | null;
  cv_across: number | null;
  runs?: number;
  best_speedup?: number | null;
  flags_speedup?: number | null;
  best_strategy?: string | null;
  best_run?: string | null;
};

export type Hotspot = { function: string; start_line: number; end_line: number; time_pct: number; loop_depth: number };

export type Profile = {
  baseline_runtime_ms: number;
  runtime_std_ms: number;
  peak_mem_kb: number;
  ipc: number | null;
  l1_miss_rate: number | null;
  llc_miss_rate: number | null;
  branch_miss_rate: number | null;
  hotspots: Hotspot[];
  counters_source: string;
  bottleneck_text: string;
};

export type Loop = { function: string | null; line: number; end_line: number; depth: number; iter_vars: string[]; array_accesses: number; innermost: boolean };

export type SweepVariant = {
  name: string;
  strategy: string;
  compiler: string;
  flags: string[];
  status: string;
  speedup?: number;
  cpu_speedup?: number;
  p_value?: number;
  positive?: boolean;
  detail?: string;
};

export type ProgramDetail = {
  id: string;
  meta: Record<string, any>;
  source: string;
  functions: string[];
  loops: Loop[];
  features: Record<string, number>;
  profile: Profile | null;
  inputs: { name: string; bytes: number; head: string }[];
  sweep: { program_id: string; variants: SweepVariant[] } | null;
  stability: { median_ms: number; cv_within_max: number; cv_across_sessions: number } | null;
  runs: RunRow[];
};

export type RunRow = {
  run_id: string;
  experiment?: string;
  program_id: string;
  category?: string;
  architecture: string;
  messaging: string;
  prompt_style: string;
  model_config?: string;
  model_assignment?: string;
  variant: string;
  success?: string;
  speedup?: string;
  cpu_speedup?: string;
  baseline_ms?: string;
  best_ms?: string;
  attempts?: string;
  total_tokens?: string;
  cost_usd?: string;
  latency_s?: string;
  winning_strategy?: string;
  stop_reason?: string;
  crit_path_agent?: string;
  error?: string;
  status: string;
  started_at?: string | number;
};

export type RunEvent = {
  type: "run_start" | "step_start" | "step_end" | "attempt_end" | "run_end" | "agent_event" | "guardrail";
  kind?: string;
  stage?: string;
  detail?: string;
  step_type?: string;
  preview?: string;
  thought?: string;
  tool?: string;
  ok?: boolean;
  t: number;
  run_id: string;
  agent?: string;
  attempt?: number | null;
  status?: string;
  dur_ms?: number;
  summary?: string;
  data?: any;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  model?: string;
  verdict?: Verdict;
  best_speedup?: number;
  config?: Record<string, any>;
  stop_reason?: string;
  error?: string;
  usage?: { prompt_tokens: number; completion_tokens: number; calls: number; cost_usd: number };
  messaging?: Record<string, any>;
};

export type Verdict = { accepted: boolean; speedup: number; reason: string; feedback_for_strategist: string; stop: boolean; stop_reason: string };

export type BenchResult = { runtimes_ms: number[]; median_ms: number; mean_ms: number; std_ms: number; p95_ms: number; cv: number; peak_mem_kb: number; cpu_median_ms: number; noisy: boolean };

export type Attempt = {
  attempt: number;
  plan: { strategies: { name: string; target: string | null; params: Record<string, any>; rationale: string; confidence: number }[]; flags: string[]; compiler: string } | null;
  candidate: { source: string; flags: string[]; diff: string; repaired: number } | null;
  build: { ok: boolean; stderr: string; flags: string[]; dropped_flags: string[] } | null;
  tests: { all_pass: boolean; failed_cases: string[]; details: Record<string, any>; sanitizer_ok: boolean | null; sanitizer_report: string } | null;
  compare: {
    speedup: number;
    p_value: number;
    cpu_speedup: number;
    baseline: BenchResult | null;
    candidate: BenchResult | null;
    vs_best_speedup?: number | null;
    vs_best_p_value?: number | null;
    low_precision?: boolean;
  } | null;
  verdict: Verdict;
};

export type RunDetail = {
  run_id: string;
  status: string;
  program_id: string;
  config: Record<string, any>;
  row?: Record<string, any>;
  state?: {
    summary: { summary_text: string; features: Record<string, number>; source: string } | null;
    profile: Profile | null;
    history: Attempt[];
    best: { speedup: number; attempt: number; candidate: { source: string; flags: string[] }; strategies?: string[] } | null;
    usage: { prompt_tokens: number; completion_tokens: number; calls: number; cost_usd: number };
    usage_by_agent: Record<string, { prompt_tokens: number; completion_tokens: number; cost_usd: number }>;
    messaging_stats: Record<string, any>;
    guardrail_events?: { agent: string; attempt: number | null; stage: string; detail: string }[];
    persona?: string;
    critic_backend?: string;
    instructions?: string;
    stop_reason: string;
    error: string;
    started_at: number;
    finished_at: number;
  };
  events: RunEvent[];
  error?: string | null;
  original_source: string;
};

export type AgentMetric = {
  agent: string;
  calls: number;
  mean_ms: number;
  median_ms: number;
  p95_ms: number;
  tokens_in_mean: number;
  tokens_out_mean: number;
  cost_usd: number;
  cost_share: number;
  critical_path_share: number;
};
