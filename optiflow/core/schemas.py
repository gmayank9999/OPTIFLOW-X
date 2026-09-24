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
]


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


class ProfileReport(BaseModel):
    baseline_runtime_ms: float
    runtime_std_ms: float
    peak_mem_kb: int
    ipc: Optional[float] = None
    l1_miss_rate: Optional[float] = None
    llc_miss_rate: Optional[float] = None
    branch_miss_rate: Optional[float] = None
    hotspots: list[Hotspot] = Field(default_factory=list)
    bottleneck_text: str = ""


class Strategy(BaseModel):
    name: StrategyName
    target: Optional[str] = None
    params: dict = Field(default_factory=dict)
    rationale: str
    confidence: float


class OptimizationPlan(BaseModel):
    attempt: int
    strategies: list[Strategy]
    compiler: Literal["gcc", "clang"] = "gcc"
    flags: list[str] = Field(default_factory=lambda: ["-O2"])


class Candidate(BaseModel):
    attempt: int
    source: str
    flags: list[str]
    diff: str = ""


class BuildResult(BaseModel):
    ok: bool
    stderr: str = ""
    binary_path: Optional[str] = None
    candidate_id: Optional[str] = None
    compile_ms: float = 0.0


class TestResult(BaseModel):
    all_pass: bool
    failed_cases: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class BenchResult(BaseModel):
    runtimes_ms: list[float]
    median_ms: float
    mean_ms: float
    std_ms: float
    p95_ms: float
    cv: float
    peak_mem_kb: int
    noisy: bool = False


class CompareResult(BaseModel):
    speedup: float
    p_value: float
    accepted_by_rule: bool


class Verdict(BaseModel):
    accepted: bool
    speedup: float = 1.0
    reason: str
    feedback_for_strategist: str = ""
    stop: bool = False


class RunState(BaseModel):
    run_id: str
    program_id: str
    architecture: str
    messaging: str
    summary: Optional[ProgramSummary] = None
    profile: Optional[ProfileReport] = None
    history: list[dict] = Field(default_factory=list)
    best: Optional[dict] = None
    budget_attempts: int = 5
