"""Shared data contracts.

Every agent and tool reads and writes only these models. Nothing crosses a
module boundary as a raw dict once it has a shape defined here.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

StrategyName = Literal[
    "flags",
    "interchange",
    "tiling",
    "vectorize",
    "unroll",
    "fusion",
    "fission",
    "soa",
    "hoist",
    "memoize",
    "algorithmic",
]

STRATEGY_NAMES: tuple[str, ...] = StrategyName.__args__  # type: ignore[attr-defined]


class Hotspot(BaseModel):
    function: str
    start_line: int
    end_line: int
    time_pct: float
    loop_depth: int


class ProgramSummary(BaseModel):
    program_id: str
    language: Literal["c", "cpp"]
    source: str
    functions: list[str]
    loops: list[dict]
    features: dict[str, float]
    summary_text: str = ""
    guardrail_findings: list[dict] = Field(default_factory=list)  # neutralized injection attempts


class ProfileReport(BaseModel):
    baseline_runtime_ms: float
    runtime_std_ms: float
    peak_mem_kb: int
    ipc: Optional[float] = None
    l1_miss_rate: Optional[float] = None
    llc_miss_rate: Optional[float] = None
    branch_miss_rate: Optional[float] = None
    hotspots: list[Hotspot] = Field(default_factory=list)
    counters_source: Literal["perf", "cachegrind", "none"] = "none"
    bottleneck_text: str = ""


class Strategy(BaseModel):
    name: StrategyName
    target: Optional[str] = None
    params: dict = Field(default_factory=dict)
    rationale: str = ""
    confidence: float = 0.5


class OptimizationPlan(BaseModel):
    attempt: int
    strategies: list[Strategy]
    compiler: Literal["gcc", "clang"] = "gcc"
    flags: list[str] = Field(default_factory=lambda: ["-O2"])


class Candidate(BaseModel):
    attempt: int
    source: str
    flags: list[str]
    compiler: Literal["gcc", "clang"] = "gcc"
    diff: str = ""
    repaired: int = 0  # number of compile self-repair rounds applied


class BuildResult(BaseModel):
    ok: bool
    stderr: str = ""
    binary_path: Optional[str] = None
    candidate_id: Optional[str] = None
    compile_ms: float = 0.0
    flags: list[str] = Field(default_factory=list)
    dropped_flags: list[str] = Field(default_factory=list)


class TestResult(BaseModel):
    all_pass: bool
    failed_cases: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)
    sanitizer_ok: Optional[bool] = None
    sanitizer_report: str = ""


class BenchResult(BaseModel):
    runtimes_ms: list[float]
    median_ms: float
    mean_ms: float
    std_ms: float
    p95_ms: float
    cv: float
    peak_mem_kb: int
    cpu_median_ms: float = 0.0
    cpu_runtimes_ms: list[float] = Field(default_factory=list)
    cpu_cv: float = 0.0
    noisy: bool = False
    failed_runs: int = 0


class CompareResult(BaseModel):
    speedup: float
    p_value: float
    accepted_by_rule: bool
    cpu_speedup: float = 0.0
    baseline: Optional[BenchResult] = None
    candidate: Optional[BenchResult] = None


class Verdict(BaseModel):
    accepted: bool
    speedup: float = 1.0
    reason: str
    feedback_for_strategist: str = ""
    stop: bool = False
    stop_reason: str = ""


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    cost_usd: float = 0.0

    def add(self, other: "TokenUsage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.calls += other.calls
        self.cost_usd += other.cost_usd


class RunState(BaseModel):
    run_id: str
    program_id: str
    architecture: str
    messaging: str
    prompt_style: str = "structured"
    model_assignment: str = "single-cloud"
    variant: str = "full"
    persona: str = "default"
    critic_backend: str = "crewai"
    instructions: str = ""
    summary: Optional[ProgramSummary] = None
    profile: Optional[ProfileReport] = None
    history: list[dict] = Field(default_factory=list)
    best: Optional[dict] = None
    budget_attempts: int = 5
    usage: TokenUsage = Field(default_factory=TokenUsage)
    usage_by_agent: dict[str, TokenUsage] = Field(default_factory=dict)
    messaging_stats: dict = Field(default_factory=dict)
    guardrail_events: list[dict] = Field(default_factory=list)
    stop_reason: str = ""
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
