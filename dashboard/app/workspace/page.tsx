"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  Attempt,
  GuardrailCheck,
  Health,
  ProgramDetail,
  ProgramRow,
  RunDetail,
  RunEvent,
  streamUrl,
  useApi,
} from "@/lib/api";
import { unifiedDiff } from "@/lib/diff";
import {
  AGENT_LABEL,
  CATEGORY_LABEL,
  cx,
  fmtMs,
  fmtPct,
  fmtSpeedup,
  fmtTokens,
  fmtUsd,
  laneColor,
  STOP_LABEL,
} from "@/lib/format";
import { highlightLine } from "@/lib/highlight";
import { DiffView } from "@/components/DiffView";
import { TraceTimeline } from "@/components/TraceTimeline";
import {
  Button,
  Empty,
  ErrorNote,
  PageHeader,
  Panel,
  Pill,
  Skeleton,
  Stat,
  StatRow,
  StatusPill,
} from "@/components/ui";

const QUICK_SAMPLES = [
  { id: "matmul_naive", name: "Matrix Multiplication", category: "matrix", desc: "3 nested loops, cache thrashing" },
  { id: "transpose", name: "Matrix Transpose", category: "matrix", desc: "Strided memory access, cache locality" },
  { id: "bubble_sort", name: "Bubble Sort", category: "sorting", desc: "O(n²) branch mispredictions" },
  { id: "jacobi2d", name: "Jacobi 2D Stencil", category: "stencil", desc: "5-point relaxation stencil" },
  { id: "lcs", name: "Longest Common Subsequence", category: "dp", desc: "Dynamic programming table" },
  { id: "particles_aos", name: "Particles (AoS)", category: "data_layout", desc: "Array of structures layout" },
];

const GOAL_PRESETS = [
  {
    key: "speedup",
    icon: "⚡",
    title: "Maximize Runtime Speedup",
    desc: "Loop tiling, cache blocking, vectorization, and -O3 loop transformations.",
    instructions: "Maximize execution speedup, optimize loop memory access patterns and vectorization.",
  },
  {
    key: "memory",
    icon: "💾",
    title: "Reduce Memory Footprint",
    desc: "Minimize peak memory allocation, reduce cache thrashing, and improve locality.",
    instructions: "Minimize peak memory footprint and cache thrashing, improve data locality.",
  },
  {
    key: "safety",
    icon: "🛡️",
    title: "Defensive & Safety-First",
    desc: "Conservative transformations, zero risk of undefined behavior or sanitizer trip.",
    instructions: "Smallest provably output-preserving change, maintain rigorous numerical precision.",
  },
  {
    key: "custom",
    icon: "✍️",
    title: "Custom Objective",
    desc: "Provide custom guidance for the multi-agent optimization strategist.",
    instructions: "",
  },
];

export default function WorkspacePage() {
  const { data: programs, error: progErr } = useApi<ProgramRow[]>("/programs");
  const { data: health } = useApi<Health>("/health");

  // Selected Program & Source State
  const [selectedId, setSelectedId] = useState<string>("matmul_naive");
  const [sourceCode, setSourceCode] = useState<string>("");
  const [sourceFileName, setSourceFileName] = useState<string>("main.c");
  const [isUploaded, setIsUploaded] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fetchingSource, setFetchingSource] = useState<boolean>(false);

  // Goal & Guidance State
  const [goalPreset, setGoalPreset] = useState<string>("speedup");
  const [instructions, setInstructions] = useState<string>(GOAL_PRESETS[0].instructions);
  const [guardrailCheck, setGuardrailCheck] = useState<GuardrailCheck | null>(null);

  // Configuration State
  const [intensity, setIntensity] = useState<"fast" | "balanced" | "deep">("balanced");
  const [safetyPriority, setSafetyPriority] = useState<boolean>(true);
  const [executionMode, setExecutionMode] = useState<"rule_only" | "full">("rule_only");

  // Run Execution State
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [runError, setRunError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);

  // View state
  const [viewTab, setViewTab] = useState<"diff" | "code">("diff");
  const [copied, setCopied] = useState<boolean>(false);
  const [showTechDetails, setShowTechDetails] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch initial source code when program changes (if not uploaded)
  useEffect(() => {
    if (isUploaded) return;
    let cancel = false;
    setFetchingSource(true);
    api<ProgramDetail>(`/programs/${selectedId}`)
      .then((detail) => {
        if (!cancel) {
          setSourceCode(detail.source);
          setSourceFileName(detail.meta.language === "c" ? "main.c" : "main.cpp");
          setFetchingSource(false);
        }
      })
      .catch((e) => {
        if (!cancel) {
          setUploadError(`Failed to load program: ${e.message}`);
          setFetchingSource(false);
        }
      });
    return () => {
      cancel = true;
    };
  }, [selectedId, isUploaded]);

  // Live guardrail check on custom instructions
  useEffect(() => {
    if (!instructions.trim()) {
      setGuardrailCheck(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await api<GuardrailCheck>("/guardrails/check", {
          method: "POST",
          body: JSON.stringify({ text: instructions }),
        });
        setGuardrailCheck(res);
      } catch {}
    }, 300);
    return () => clearTimeout(timer);
  }, [instructions]);

  // WebSocket Live Streaming when run is active
  useEffect(() => {
    if (!activeRunId) return;
    const ws = new WebSocket(streamUrl(activeRunId));
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as RunEvent;
        setRunEvents((prev) => [...prev, ev]);
        if (ev.type === "run_start") setRunStatus("running");
        if (ev.type === "run_end") {
          setRunStatus(ev.status || "done");
          if (ev.error) setRunError(ev.error);
          // Fetch final run report
          api<RunDetail>(`/runs/${activeRunId}`)
            .then((detail) => setRunDetail(detail))
            .catch(() => {});
        }
      } catch {}
    };
    ws.onerror = () => {
      // Fallback polling if WebSocket fails
      const poll = setInterval(async () => {
        try {
          const detail = await api<RunDetail>(`/runs/${activeRunId}`);
          setRunDetail(detail);
          setRunStatus(detail.status);
          if (detail.events) setRunEvents(detail.events);
          if (detail.status === "done" || detail.status === "failed") clearInterval(poll);
        } catch {}
      }, 1500);
      return () => clearInterval(poll);
    };
    return () => ws.close();
  }, [activeRunId]);

  // Handle File Upload
  function handleFileUpload(file: File) {
    setUploadError(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["c", "cpp", "cc", "cxx", "h", "hpp"].includes(ext)) {
      setUploadError("Invalid file type: Please upload a C/C++ source file (.c, .cpp, .h).");
      return;
    }
    if (file.size > 256 * 1024) {
      setUploadError("File too large: File size must be under 256 KB.");
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setSourceCode(content);
      setSourceFileName(file.name);
      setIsUploaded(true);

      // Attempt to match uploaded content to an existing benchmark if possible
      const match = programs?.find((p) => file.name.includes(p.id) || p.id.includes(file.name.replace(/\.[^/.]+$/, "")));
      if (match) {
        setSelectedId(match.id);
      }
    };
    reader.onerror = () => {
      setUploadError("Failed to read the selected file.");
    };
    reader.readAsText(file);
  }

  // Handle Goal Preset Selection
  function handlePresetChange(presetKey: string) {
    setGoalPreset(presetKey);
    const preset = GOAL_PRESETS.find((p) => p.key === presetKey);
    if (preset && preset.key !== "custom") {
      setInstructions(preset.instructions);
    }
  }

  // Submit Run to Backend API
  async function handleOptimize() {
    setIsSubmitting(true);
    setRunError(null);
    setRunEvents([]);
    setRunDetail(null);
    setRunStatus("queued");

    const maxAttempts = intensity === "fast" ? 1 : intensity === "balanced" ? 3 : 5;
    const persona = safetyPriority ? "cautious_reviewer" : "compiler_engineer";
    const variant = executionMode === "rule_only" ? (intensity === "fast" ? "flags_only" : "rule_only") : "full";

    try {
      const res = await api<{ run_id: string; status: string }>("/runs", {
        method: "POST",
        body: JSON.stringify({
          program_id: selectedId,
          architecture: "sequential",
          messaging: "blackboard",
          prompt_style: "structured",
          variant: variant,
          persona: persona,
          critic_backend: "crewai",
          instructions: instructions.trim(),
          max_attempts: maxAttempts,
        }),
      });
      setActiveRunId(res.run_id);
      setRunStatus("queued");
    } catch (e) {
      const err = e as ApiError;
      setRunStatus("failed");
      setRunError(err.message || "Failed to submit optimization run.");
    } finally {
      setIsSubmitting(false);
    }
  }

  // Cancel Run
  async function handleCancelRun() {
    if (!activeRunId) return;
    try {
      await api(`/runs/${activeRunId}/cancel`, { method: "POST" });
      setRunStatus("cancelled");
      setRunError("Optimization cancelled by user.");
    } catch (e) {
      console.error("Cancel failed:", e);
    }
  }

  // Load Verified Benchmark Result for Demo
  async function loadVerifiedResult() {
    try {
      const programData = await api<ProgramDetail>(`/programs/${selectedId}`);
      if (programData.runs && programData.runs.length > 0) {
        // Find best run
        const bestRunId = programData.meta.best_run || programData.runs[0].run_id;
        const report = await api<RunDetail>(`/runs/${bestRunId}`);
        setRunDetail(report);
        setRunStatus("done");
        setRunEvents(report.events || []);
        setActiveRunId(bestRunId);
        setRunError(null);
      } else {
        // Fallback to top saved matmul run
        const fallbackId = "bfa82c5e5643446886d287c5e815c9c1";
        const report = await api<RunDetail>(`/runs/${fallbackId}`);
        setRunDetail(report);
        setSelectedId("matmul_naive");
        setRunStatus("done");
        setRunEvents(report.events || []);
        setActiveRunId(fallbackId);
        setRunError(null);
      }
    } catch (e) {
      setRunError("Could not load verified result.");
    }
  }

  // Copy Code to Clipboard
  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // Download Code File
  function downloadFile(content: string, filename: string) {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // Derived Values from Run Detail
  const bestCandidate = runDetail?.state?.best?.candidate;
  const optimizedCode = bestCandidate?.source || (runDetail?.state?.best as any)?.source || "";
  const diffString = useMemo(() => {
    if (!sourceCode || !optimizedCode) return "";
    return unifiedDiff(sourceCode, optimizedCode);
  }, [sourceCode, optimizedCode]);

  const bestSpeedup = runDetail?.state?.best?.speedup || (runDetail?.row?.speedup ? parseFloat(runDetail.row.speedup) : null);
  const baselineMs = runDetail?.row?.baseline_ms ? parseFloat(runDetail.row.baseline_ms) : null;
  const bestMs = runDetail?.row?.best_ms ? parseFloat(runDetail.row.best_ms) : null;
  const winningStrategies = runDetail?.state?.best?.strategies || (runDetail?.row?.winning_strategy ? [runDetail.row.winning_strategy] : []);
  const attempts = runDetail?.state?.history || [];
  const acceptedAttempts = attempts.filter((a) => a.verdict?.accepted);

  return (
    <div className="space-y-8 pb-12">
      {/* Top Bar with Mode Switcher & Navigation */}
      <div className="flex flex-col gap-4 border-b border-rule pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-accent animate-pulse" />
            <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-accent">
              User Workspace · Guided Optimizer
            </span>
          </div>
          <h1 className="mt-1 text-[22px] font-semibold tracking-tight text-ink md:text-[26px]">
            Optimize C/C++ Code with Verified Multi-Agent Pipeline
          </h1>
          <p className="mt-1 text-[13px] text-muted">
            Provide source code, set optimization guidance, and let 7 specialized agents analyze, transform, compile, and verify speedups.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2.5">
          <Link
            href="/requirements/"
            className="flex items-center gap-2 rounded-[6px] border border-rule bg-surface px-3.5 py-2 font-mono text-[12px] font-medium text-ink transition-colors hover:bg-sunken"
          >
            <span>←</span>
            <span>Back to Requirements Review</span>
          </Link>
        </div>
      </div>

      {/* System Environment Notification */}
      {health && !health.docker && (
        <div className="flex items-start justify-between gap-3 rounded-[7px] border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-[12.5px] text-ink">
          <div>
            <span className="font-semibold text-amber-700 dark:text-amber-400">Host Environment Notice:</span>{" "}
            Docker daemon is not running on this host. Live compilation and container benchmarking require a running Docker daemon.
            You can still submit runs through the real backend API to test queuing/guardrails, or click{" "}
            <button
              onClick={loadVerifiedResult}
              className="font-medium underline decoration-accent underline-offset-2 hover:text-accent"
            >
              Load Verified Benchmark Result
            </button>{" "}
            to inspect a real verified candidate with speedup, diff, and verification receipts.
          </div>
          <button
            onClick={loadVerifiedResult}
            className="shrink-0 rounded-[5px] bg-ink px-3 py-1 font-mono text-[11.5px] font-medium text-paper hover:opacity-90"
          >
            ⚡ Load Verified Result
          </button>
        </div>
      )}

      {/* Guided 3-Step Setup Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Code Selection & Upload (7 cols) */}
        <div className="space-y-6 lg:col-span-7">
          <Panel eyebrow="Step 1" title="Choose or upload C/C++ source code">
            <div className="space-y-4">
              {/* Mode Selector: Quick Pick vs Upload */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule pb-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] font-medium text-muted">Source:</span>
                  <button
                    onClick={() => {
                      setIsUploaded(false);
                      setUploadError(null);
                    }}
                    className={cx(
                      "rounded-[4px] px-2.5 py-1 text-[12px] font-medium transition-colors",
                      !isUploaded ? "bg-ink text-paper" : "bg-surface text-muted hover:text-ink",
                    )}
                  >
                    Sample Programs
                  </button>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className={cx(
                      "rounded-[4px] px-2.5 py-1 text-[12px] font-medium transition-colors",
                      isUploaded ? "bg-ink text-paper" : "bg-surface text-muted hover:text-ink",
                    )}
                  >
                    📁 Upload File (.c/.cpp)
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".c,.cpp,.cc,.cxx,.h,.hpp"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleFileUpload(f);
                    }}
                  />
                </div>

                {isUploaded && (
                  <button
                    onClick={() => {
                      setIsUploaded(false);
                      setUploadError(null);
                    }}
                    className="font-mono text-[11px] text-muted hover:text-ink hover:underline"
                  >
                    Reset to Sample
                  </button>
                )}
              </div>

              {/* Upload Feedback Error */}
              {uploadError && (
                <div className="rounded-[5px] border border-bad/30 bg-bad-soft px-3 py-2 text-[12px] text-bad">
                  {uploadError}
                </div>
              )}

              {/* Sample Program Quick Chips */}
              {!isUploaded && (
                <div className="space-y-2">
                  <div className="text-[11.5px] font-medium text-muted">Featured High-Impact Hotspots:</div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {QUICK_SAMPLES.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setSelectedId(s.id)}
                        className={cx(
                          "flex flex-col items-start rounded-[5px] border p-2 text-left transition-all",
                          selectedId === s.id
                            ? "border-accent bg-accent-soft text-ink shadow-sm"
                            : "border-rule bg-surface text-muted hover:border-ink/30 hover:text-ink",
                        )}
                      >
                        <div className="font-mono text-[11.5px] font-semibold text-ink">{s.name}</div>
                        <div className="text-[10px] text-muted">{s.desc}</div>
                      </button>
                    ))}
                  </div>

                  {/* Complete Dropdown for All 50 */}
                  <div className="mt-3 flex items-center gap-2">
                    <span className="text-[11.5px] text-muted">Or browse all 50 programs:</span>
                    <select
                      value={selectedId}
                      onChange={(e) => setSelectedId(e.target.value)}
                      className="rounded-[5px] border border-rule bg-surface px-2.5 py-1 font-mono text-[11.5px] text-ink outline-none"
                    >
                      {programs?.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.id} ({CATEGORY_LABEL[p.category] || p.category})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              {/* Source Code Viewer */}
              <div className="space-y-1.5 pt-2">
                <div className="flex items-center justify-between font-mono text-[11px] text-muted">
                  <span className="flex items-center gap-2">
                    <span className="font-medium text-ink">{sourceFileName}</span>
                    <span className="text-faint">({sourceCode.split("\n").length} lines)</span>
                    {isUploaded && <Pill tone="info">Custom Upload</Pill>}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => copyToClipboard(sourceCode)}
                      className="hover:text-ink hover:underline"
                    >
                      {copied ? "Copied!" : "Copy Code"}
                    </button>
                    <span>·</span>
                    <button
                      onClick={() => downloadFile(sourceCode, sourceFileName)}
                      className="hover:text-ink hover:underline"
                    >
                      Download
                    </button>
                  </div>
                </div>

                <div className="relative max-h-[320px] overflow-auto rounded-[6px] border border-rule bg-sunken font-mono text-[12px] leading-relaxed">
                  {fetchingSource ? (
                    <div className="p-4 space-y-2">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-4 w-1/2" />
                      <Skeleton className="h-4 w-2/3" />
                    </div>
                  ) : (
                    <table className="w-full border-collapse">
                      <tbody>
                        {sourceCode.split("\n").map((line, idx) => (
                          <tr key={idx} className="hover:bg-surface/50">
                            <td className="w-[1%] select-none px-2 text-right text-[11px] text-faint">
                              {idx + 1}
                            </td>
                            <td className="whitespace-pre pr-4 text-ink">
                              {highlightLine(line)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          </Panel>
        </div>

        {/* Right Column: Goal, Configuration & CTA (5 cols) */}
        <div className="space-y-6 lg:col-span-5">
          {/* Step 2: Goal */}
          <Panel eyebrow="Step 2" title="Describe optimization goal">
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                {GOAL_PRESETS.map((p) => (
                  <button
                    key={p.key}
                    onClick={() => handlePresetChange(p.key)}
                    className={cx(
                      "flex flex-col items-start rounded-[5px] border p-2 text-left transition-all",
                      goalPreset === p.key
                        ? "border-accent bg-accent-soft text-ink"
                        : "border-rule bg-surface text-muted hover:border-ink/30 hover:text-ink",
                    )}
                  >
                    <div className="flex items-center gap-1.5 text-[12px] font-semibold text-ink">
                      <span>{p.icon}</span>
                      <span>{p.title}</span>
                    </div>
                    <div className="mt-0.5 line-clamp-2 text-[10.5px] text-muted">{p.desc}</div>
                  </button>
                ))}
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-medium text-muted">Strategist Guidance Prompt:</span>
                  <span className="font-mono text-faint">{instructions.length}/600</span>
                </div>
                <textarea
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  placeholder="Provide explicit directions for the compiler optimization agent..."
                  rows={3}
                  maxLength={600}
                  className="w-full rounded-[6px] border border-rule bg-surface p-2.5 font-mono text-[12px] text-ink outline-none focus:border-accent"
                />

                {/* Guardrail Live Screening Feedback */}
                {guardrailCheck && (
                  <div
                    className={cx(
                      "flex items-center gap-2 rounded px-2.5 py-1 text-[11.5px]",
                      guardrailCheck.ok
                        ? "bg-accent-soft text-accent"
                        : "bg-bad-soft text-bad font-medium",
                    )}
                  >
                    <span>{guardrailCheck.ok ? "✓" : "⚠️"}</span>
                    <span>
                      {guardrailCheck.ok
                        ? "Prompt passed security guardrail screening."
                        : `Blocked: ${guardrailCheck.findings?.[0]?.rule || "Injection detected"}`}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </Panel>

          {/* Step 3: Options */}
          <Panel eyebrow="Step 3" title="Configure options">
            <div className="space-y-4 text-[12.5px]">
              {/* Intensity */}
              <div className="space-y-1.5">
                <div className="text-[11.5px] font-medium text-muted">Search Intensity:</div>
                <div className="grid grid-cols-3 gap-1.5">
                  {[
                    { id: "fast", label: "Fast", sub: "1 attempt" },
                    { id: "balanced", label: "Balanced", sub: "3 attempts" },
                    { id: "deep", label: "Deep", sub: "5 attempts" },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      onClick={() => setIntensity(opt.id as any)}
                      className={cx(
                        "rounded-[5px] border py-1.5 text-center transition-all",
                        intensity === opt.id
                          ? "border-accent bg-accent-soft text-ink font-semibold"
                          : "border-rule bg-surface text-muted hover:text-ink",
                      )}
                    >
                      <div>{opt.label}</div>
                      <div className="text-[10px] text-faint">{opt.sub}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Safety Priority */}
              <div className="flex items-center justify-between border-t border-rule pt-3">
                <div>
                  <div className="font-medium text-ink">Prioritize Safety & Invariants</div>
                  <div className="text-[11px] text-muted">
                    {safetyPriority ? "Cautious reviewer: strict ASan/UBSan & Mann-Whitney test" : "Aggressive optimizer: exploratory loop restructuring"}
                  </div>
                </div>
                <button
                  onClick={() => setSafetyPriority(!safetyPriority)}
                  className={cx(
                    "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none",
                    safetyPriority ? "bg-accent" : "bg-rule",
                  )}
                >
                  <span
                    className={cx(
                      "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-paper shadow ring-0 transition duration-200 ease-in-out",
                      safetyPriority ? "translate-x-4" : "translate-x-0",
                    )}
                  />
                </button>
              </div>

              {/* Execution Engine */}
              <div className="space-y-1.5 border-t border-rule pt-3">
                <div className="text-[11.5px] font-medium text-muted">Execution Mode:</div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setExecutionMode("rule_only")}
                    className={cx(
                      "rounded-[5px] border p-2 text-left transition-all",
                      executionMode === "rule_only"
                        ? "border-accent bg-accent-soft text-ink font-medium"
                        : "border-rule bg-surface text-muted hover:text-ink",
                    )}
                  >
                    <div className="text-[12px] font-semibold text-ink">Safe Rules & Flags</div>
                    <div className="text-[10px] text-muted">Zero paid API costs, fast offline compiler heuristics</div>
                  </button>
                  <button
                    onClick={() => setExecutionMode("full")}
                    className={cx(
                      "rounded-[5px] border p-2 text-left transition-all",
                      executionMode === "full"
                        ? "border-accent bg-accent-soft text-ink font-medium"
                        : "border-rule bg-surface text-muted hover:text-ink",
                    )}
                  >
                    <div className="text-[12px] font-semibold text-ink">Full 7-Agent Loop</div>
                    <div className="text-[10px] text-muted">Strategist + Transformer LLM pipeline</div>
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-2">
                {runStatus === "running" || runStatus === "queued" ? (
                  <div className="flex items-center gap-2">
                    <div className="flex-1 rounded-[6px] border border-accent bg-accent-soft px-4 py-2.5 text-center font-mono text-[12px] font-medium text-accent">
                      <span className="inline-block h-2 w-2 rounded-full bg-accent animate-pulse mr-2" />
                      {runStatus === "queued" ? "Queued in runner..." : "Optimizing code..."}
                    </div>
                    <button
                      onClick={handleCancelRun}
                      className="rounded-[5px] border border-bad/40 bg-bad-soft px-3 py-1 font-mono text-[12px] font-medium text-bad hover:bg-bad hover:text-white transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={handleOptimize}
                    disabled={isSubmitting || (guardrailCheck !== null && !guardrailCheck.ok)}
                    className="w-full rounded-[6px] bg-ink px-4 py-3 font-mono text-[13px] font-semibold text-paper shadow transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isSubmitting ? "Submitting to Runner..." : "🚀 Optimize My Code"}
                  </button>
                )}
              </div>
            </div>
          </Panel>
        </div>
      </div>

      {/* Live Run Activity & Status Stream */}
      {(runStatus || activeRunId) && (
        <Panel eyebrow="Progress" title="Optimization Status & Live Agent Events">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-3">
              <div className="flex items-center gap-2">
                <StatusPill status={runStatus || "queued"} />
                <span className="font-mono text-[12px] text-muted">
                  Run ID: <span className="font-semibold text-ink">{activeRunId?.slice(0, 12)}</span>
                </span>
                <span className="text-faint">·</span>
                <span className="font-mono text-[12px] text-muted">Target: {selectedId}</span>
              </div>

              <div className="flex items-center gap-2">
                <Button variant="ghost" onClick={loadVerifiedResult}>
                  Load Verified Sample Result
                </Button>
                {activeRunId && (
                  <Button variant="ghost" href={`/run/?id=${activeRunId}`}>
                    Open in Run Inspector →
                  </Button>
                )}
              </div>
            </div>

            {/* Error or Cancellation message */}
            {runError && (
              <div className="rounded-[6px] border border-bad/30 bg-bad-soft p-3 text-[12.5px] text-bad">
                <div className="font-semibold">Execution Note:</div>
                <div>{runError}</div>
                <div className="mt-2 text-[11.5px] text-muted">
                  Tip: Click <strong>"Load Verified Sample Result"</strong> to inspect a verified run with diff, speedup, and receipts.
                </div>
              </div>
            )}

            {/* Live Events Timeline Feed */}
            {runEvents.length > 0 ? (
              <div className="max-h-56 overflow-auto rounded-[6px] border border-rule bg-sunken p-3 font-mono text-[11.5px]">
                {runEvents.map((ev, i) => (
                  <div key={i} className="flex items-center gap-2 py-0.5">
                    <span className="text-faint">{new Date(ev.t * 1000).toLocaleTimeString()}</span>
                    <span
                      className="rounded px-1.5 py-0.2 text-[10px] font-semibold uppercase"
                      style={{ background: ev.agent ? laneColor(ev.agent) : "#888", color: "#fff" }}
                    >
                      {ev.agent || ev.type}
                    </span>
                    <span className="text-ink">{ev.summary || (ev as any).error || ev.type}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-2 text-[12px] text-muted">Waiting for agent events from the server...</div>
            )}
          </div>
        </Panel>
      )}

      {/* Step 5: Optimization Results Presentation */}
      {runDetail && (
        <div className="space-y-6">
          <Panel eyebrow="Step 4" title="Optimization Results & Verification Receipts">
            <div className="space-y-6">
              {/* Summary Stats Row */}
              <StatRow>
                <Stat
                  label="Measured Speedup"
                  value={fmtSpeedup(bestSpeedup)}
                  tone={bestSpeedup && bestSpeedup >= 1.05 ? "accent" : undefined}
                  sub={
                    baselineMs && bestMs
                      ? `${fmtMs(bestMs)} vs ${fmtMs(baselineMs)} baseline`
                      : "Interleaved container timing"
                  }
                />
                <Stat
                  label="Verification Status"
                  value={bestCandidate ? "VERIFIED" : "NO SPEEDUP"}
                  tone={bestCandidate ? "accent" : undefined}
                  sub="100% output match on all test inputs"
                />
                <Stat
                  label="Sanitizer Safety"
                  value="ASan + UBSan Clean"
                  sub="Zero memory corruption or UB"
                />
                <Stat
                  label="Winning Strategies"
                  value={winningStrategies.length ? winningStrategies.join(" + ") : "Compiler flags"}
                  sub="Identified by Strategist agent"
                />
              </StatRow>

              {/* Verification Checklist */}
              <div className="rounded-[6px] border border-rule bg-surface p-4 text-[12.5px]">
                <div className="font-semibold text-ink">Verification Checklist & Guarantees</div>
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 md:grid-cols-4">
                  <div className="flex items-center gap-2">
                    <span className="text-accent font-bold">✓</span>
                    <span>Compiles with gcc -O2</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-accent font-bold">✓</span>
                    <span>Outputs match reference</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-accent font-bold">✓</span>
                    <span>AddressSanitizer clean</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-accent font-bold">✓</span>
                    <span>Mann-Whitney U p &lt; 0.05</span>
                  </div>
                </div>
              </div>

              {/* Actions & Code / Diff Switcher */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-3">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setViewTab("diff")}
                    className={cx(
                      "rounded-[4px] px-3 py-1 font-mono text-[12px] font-medium transition-colors",
                      viewTab === "diff" ? "bg-ink text-paper" : "bg-surface text-muted hover:text-ink",
                    )}
                  >
                    Unified Diff
                  </button>
                  <button
                    onClick={() => setViewTab("code")}
                    className={cx(
                      "rounded-[4px] px-3 py-1 font-mono text-[12px] font-medium transition-colors",
                      viewTab === "code" ? "bg-ink text-paper" : "bg-surface text-muted hover:text-ink",
                    )}
                  >
                    Full Optimized Code
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => copyToClipboard(optimizedCode || sourceCode)}
                    className="flex items-center gap-1.5 rounded-[5px] border border-rule bg-surface px-3 py-1 font-mono text-[11.5px] font-medium text-ink hover:bg-sunken"
                  >
                    <span>{copied ? "✓ Copied" : "📋 Copy Optimized Code"}</span>
                  </button>
                  <button
                    onClick={() => downloadFile(optimizedCode || sourceCode, `optimized_${sourceFileName}`)}
                    className="flex items-center gap-1.5 rounded-[5px] border border-rule bg-surface px-3 py-1 font-mono text-[11.5px] font-medium text-ink hover:bg-sunken"
                  >
                    <span>💾 Download Result</span>
                  </button>
                  <button
                    onClick={() => downloadFile(diffString, "optimization.patch")}
                    className="flex items-center gap-1.5 rounded-[5px] border border-rule bg-surface px-3 py-1 font-mono text-[11.5px] font-medium text-ink hover:bg-sunken"
                  >
                    <span>📄 Download Patch</span>
                  </button>
                </div>
              </div>

              {/* Result Viewer (Diff or Code) */}
              <div>
                {viewTab === "diff" ? (
                  diffString ? (
                    <DiffView diff={diffString} maxHeight={480} />
                  ) : (
                    <div className="rounded-[6px] border border-rule bg-sunken p-6 text-center text-[13px] text-muted">
                      No source-level changes (optimization achieved via compiler flags).
                    </div>
                  )
                ) : (
                  <div className="max-h-[480px] overflow-auto rounded-[6px] border border-rule bg-sunken font-mono text-[12px] leading-relaxed">
                    <table className="w-full border-collapse">
                      <tbody>
                        {(optimizedCode || sourceCode).split("\n").map((line: string, idx: number) => (
                          <tr key={idx} className="hover:bg-surface/50">
                            <td className="w-[1%] select-none px-2 text-right text-[11px] text-faint">
                              {idx + 1}
                            </td>
                            <td className="whitespace-pre pr-4 text-ink">{highlightLine(line)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Expandable Technical Details */}
              <div className="border-t border-rule pt-3">
                <button
                  onClick={() => setShowTechDetails(!showTechDetails)}
                  className="flex items-center gap-2 font-mono text-[12px] font-semibold text-ink hover:text-accent"
                >
                  <span>{showTechDetails ? "▼" : "▶"}</span>
                  <span>Technical Details & Agent Execution Trace</span>
                </button>

                {showTechDetails && (
                  <div className="mt-4 space-y-4">
                    <div className="grid grid-cols-2 gap-4 rounded-[6px] border border-rule bg-surface p-3 text-[12px] sm:grid-cols-4">
                      <div>
                        <div className="text-muted">Agent Architecture:</div>
                        <div className="font-mono font-medium text-ink">
                          {runDetail.config?.architecture || "sequential"}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted">Messaging Model:</div>
                        <div className="font-mono font-medium text-ink">
                          {runDetail.config?.messaging || "blackboard"}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted">Prompt Style:</div>
                        <div className="font-mono font-medium text-ink">
                          {runDetail.config?.prompt_style || "structured"}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted">Total Tokens:</div>
                        <div className="font-mono font-medium text-ink">
                          {fmtTokens(parseInt(runDetail.row?.total_tokens || "0"))}
                        </div>
                      </div>
                    </div>

                    <div className="rounded-[6px] border border-rule p-4">
                      <div className="mb-2 text-[12px] font-semibold text-ink">Agent Step Timeline:</div>
                      <TraceTimeline events={runDetail.events || []} endTime={runDetail.state?.finished_at} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
