import type { Attempt, BenchResult, RunDetail, RunEvent } from "@/lib/api";

export const MAX_SOURCE_BYTES = 256 * 1024;
export const MAX_INPUT_BYTES = 1024 * 1024;
export const MAX_TEST_INPUTS = 3;
export const SOURCE_EXTENSIONS = ["c", "cpp", "cc", "cxx"];

export type Language = "c" | "cpp";

export function detectLanguage(code: string, fileName?: string): Language {
  const ext = fileName?.split(".").pop()?.toLowerCase();
  if (ext === "c") return "c";
  if (ext && SOURCE_EXTENSIONS.includes(ext)) return "cpp";
  return /#include\s*<(iostream|vector|string|algorithm|map|set|cmath|bits\/stdc\+\+\.h)>|\bstd::|\bnamespace\b|\btemplate\s*<|\bclass\s+\w+/.test(code) ? "cpp" : "c";
}

/** A message for the user, or null when the code can be submitted. */
export function validateCode(code: string): string | null {
  if (!code.trim()) return "There's no code yet. Paste a program, upload a file, or pick a sample.";
  if (new Blob([code]).size > MAX_SOURCE_BYTES) return `This code is larger than ${MAX_SOURCE_BYTES / 1024} KB. Please use a smaller program.`;
  if (!/\bmain\b/.test(code)) return "We couldn't find a main() function. The program needs to be complete so we can run it.";
  return null;
}

export function validateFile(file: File): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!SOURCE_EXTENSIONS.includes(ext)) return `"${file.name}" isn't a C/C++ source file. Please choose a .c, .cpp, .cc or .cxx file.`;
  if (file.size === 0) return `"${file.name}" is empty.`;
  if (file.size > MAX_SOURCE_BYTES) return `"${file.name}" is larger than ${MAX_SOURCE_BYTES / 1024} KB.`;
  return null;
}

export function validateTestInput(text: string, index: number): string | null {
  if (new Blob([text]).size > MAX_INPUT_BYTES) return `Example input ${index + 1} is larger than ${MAX_INPUT_BYTES / 1024} KB.`;
  return null;
}

export const GOALS = [
  { key: "speed", icon: "⚡", title: "Make it faster", desc: "Cut running time. The best choice for most programs.", instructions: "Maximize execution speedup, optimize loop memory access patterns and vectorization." },
  { key: "memory", icon: "🧠", title: "Use memory better", desc: "Improve how data is laid out and reused to avoid slow memory access.", instructions: "Minimize peak memory footprint and cache thrashing, improve data locality." },
  { key: "safe", icon: "🛡️", title: "Play it safe", desc: "Only small, low-risk changes that keep the output exactly the same.", instructions: "Smallest provably output-preserving change, maintain rigorous numerical precision." },
  { key: "custom", icon: "✍️", title: "Describe it myself", desc: "Tell the optimizer in your own words what matters.", instructions: "" },
] as const;
export type GoalKey = (typeof GOALS)[number]["key"];

export const SAMPLES = [
  { id: "matmul_naive", name: "Matrix multiplication", desc: "Three nested loops" },
  { id: "transpose", name: "Matrix transpose", desc: "Jumps around in memory" },
  { id: "bubble_sort", name: "Bubble sort", desc: "A classic slow sort" },
  { id: "jacobi2d", name: "Grid smoothing", desc: "Neighbour averaging" },
  { id: "lcs", name: "Longest common subsequence", desc: "Dynamic programming" },
  { id: "particles_aos", name: "Particle simulation", desc: "Struct-heavy data" },
];

/** Plain-language names for what the pipeline's agents do. */
const STAGES: { agent: string; label: string; always: boolean }[] = [
  { agent: "analyzer", label: "Reading your code", always: true },
  { agent: "profiler", label: "Measuring where the time goes", always: true },
  { agent: "strategist", label: "Planning improvements", always: true },
  { agent: "transformer", label: "Rewriting the code", always: false },
  { agent: "compiler_exec", label: "Compiling and checking the output", always: true },
  { agent: "benchmark", label: "Timing it against your original", always: true },
  { agent: "critic", label: "Reviewing the result", always: false },
];

export type Stage = { label: string; state: "done" | "active" | "waiting" };

/** Stage checklist driven by the real step_start / step_end events. A stage
 *  repeats once per attempt, so it is "active" while its latest event is a start. */
export function stagesFrom(events: RunEvent[]): Stage[] {
  const last = new Map<string, "start" | "end">();
  for (const e of events) {
    if (!e.agent) continue;
    if (e.type === "step_start") last.set(e.agent, "start");
    if (e.type === "step_end") last.set(e.agent, "end");
  }
  return STAGES.filter((s) => s.always || last.has(s.agent)).map((s) => {
    const seen = last.get(s.agent);
    return { label: s.label, state: seen === "start" ? "active" : seen === "end" ? "done" : "waiting" };
  });
}

export type Validation = "verified" | "output_only" | "unverified";

export type Outcome = {
  kind: "improved" | "no_gain" | "failed" | "cancelled" | "incomplete";
  message: string;
  validation: Validation | null;
  validationNote: string;
  originalSource: string;
  optimizedSource: string;
  sourceChanged: boolean;
  flags: string[];
  originalMs: number | null;
  optimizedMs: number | null;
  speedup: number | null;
  pValue: number | null;
  lowPrecision: boolean;
  attempts: number;
  accepted: Attempt | null;
};

const medianOf = (b: BenchResult | null | undefined) => (b && Number.isFinite(b.median_ms) ? b.median_ms : null);

/** Everything shown in the results view comes from the run report. Nothing
 *  is marked correct unless the accepted attempt's own tests say so. */
export function deriveOutcome(run: RunDetail): Outcome {
  const state = run.state;
  const history = state?.history ?? [];
  const best = state?.best ?? null;
  const originalSource = run.original_source || state?.summary?.source || "";
  const base: Outcome = {
    kind: "incomplete", message: "", validation: null, validationNote: "", originalSource,
    optimizedSource: originalSource, sourceChanged: false, flags: [], originalMs: null, optimizedMs: null,
    speedup: null, pValue: null, lowPrecision: false, attempts: history.length, accepted: null,
  };

  const error = (run.error || state?.error || "").trim();
  if (run.status === "cancelled") return { ...base, kind: "cancelled", message: "The optimization was stopped before it finished." };
  if (run.status === "failed" || error) {
    return { ...base, kind: "failed", message: error || "The optimization could not be completed." };
  }
  if (!state) return { ...base, message: "The run hasn't produced a result yet." };

  const accepted = best && best.attempt > 0 ? history.find((h) => h.attempt === best.attempt && h.verdict?.accepted) ?? null : null;
  if (!best || !accepted) {
    return {
      ...base, kind: "no_gain", flags: best?.candidate?.flags ?? [],
      message: "We couldn't find a version that is both faster and gives exactly the same output, so your code is unchanged.",
    };
  }

  const tests = accepted.tests;
  let validation: Validation = "unverified";
  let validationNote = "No test results were recorded for this version.";
  if (tests?.all_pass) {
    if (tests.sanitizer_ok === true) {
      validation = "verified";
      validationNote = "It produced the same output as your original on every test input, and a memory-safety check found no problems.";
    } else if (tests.sanitizer_ok === false) {
      validationNote = "The output matched, but the memory-safety check reported a problem. Don't use this version.";
    } else {
      validation = "output_only";
      validationNote = "It produced the same output as your original on every test input. The memory-safety check could not run.";
    }
  } else if (tests) {
    validationNote = "Some test inputs gave different output than your original.";
  }

  const source = best.candidate.source || originalSource;
  const cmp = accepted.compare;
  return {
    ...base,
    kind: "improved",
    validation,
    validationNote,
    optimizedSource: source,
    sourceChanged: source.trim() !== originalSource.trim(),
    flags: best.candidate.flags ?? [],
    originalMs: medianOf(cmp?.baseline),
    optimizedMs: medianOf(cmp?.candidate),
    speedup: cmp?.speedup ?? best.speedup ?? null,
    pValue: cmp?.p_value ?? null,
    lowPrecision: !!cmp?.low_precision,
    accepted,
  };
}

/** One short line describing what is happening, from the latest event. */
export function latestStatus(events: RunEvent[]): string {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "run_end") continue;
    const text = e.summary || e.detail;
    if (text) return text;
  }
  return "";
}
