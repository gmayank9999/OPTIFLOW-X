"""Environment configuration, model routing and token pricing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# CrewAI sends anonymous usage telemetry to its servers by default. Off
# unless explicitly re-enabled in .env (CREWAI_DISABLE_TELEMETRY=false).
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

# USD per 1M tokens, (input, output). Local models are free but still timed.
PRICE_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gemini/gemini-flash-lite-latest": (0.10, 0.40),
    "gemini/gemini-2.0-flash": (0.10, 0.40),
    "gemini/gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini/gemini-2.5-flash": (0.30, 2.50),
    "gemini/gemini-flash-latest": (0.30, 2.50),
    "groq/llama-3.3-70b-versatile": (0.59, 0.79),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4.1-mini": (0.40, 1.60),
    "ollama/qwen2.5-coder:7b": (0.0, 0.0),
}

ROLES = (
    "analyzer", "profiler", "strategist", "transformer",
    "compiler_exec", "benchmark", "critic", "manager", "judge",
)

MODEL_ASSIGNMENT_NAMES = ("single-cloud", "single-local", "mixed")


def data_dir(sub: str, default_root: str = "results") -> "pathlib.Path":
    """Where files a deployed server *writes* (run reports, traces, user
    programs) live. OPTIFLOW_DATA_DIR points at a persistent disk; unset,
    they go under results/ as before. Committed evidence (runs.csv,
    stability.json, ...) is always read from results/, never from here."""
    import pathlib

    root = os.getenv("OPTIFLOW_DATA_DIR")
    return pathlib.Path(root) / sub if root else pathlib.Path(default_root) / sub


@dataclass(frozen=True)
class Settings:
    cloud_model: str
    strong_model: str
    local_model: str
    judge_model: str
    max_attempts: int
    max_usd_per_run: float
    sandbox_image: str
    sandbox_cpuset: str
    model_assignment: str = "single-cloud"


@lru_cache
def get_settings() -> Settings:
    cloud = os.getenv("CLOUD_MODEL", "gemini/gemini-flash-lite-latest")
    return Settings(
        cloud_model=cloud,
        strong_model=os.getenv("STRONG_MODEL", "openai/gpt-4o-mini"),
        local_model=os.getenv("LOCAL_MODEL", "ollama/qwen2.5-coder:7b"),
        judge_model=os.getenv("JUDGE_MODEL", cloud),
        max_attempts=int(os.getenv("MAX_ATTEMPTS", "5")),
        max_usd_per_run=float(os.getenv("MAX_USD_PER_RUN", "0.05")),
        sandbox_image=os.getenv("SANDBOX_IMAGE", "optiflow-sandbox"),
        sandbox_cpuset=os.getenv("SANDBOX_CPUSET", "2"),
        model_assignment=os.getenv("MODEL_ASSIGNMENT", "single-cloud"),
    )


def model_assignments() -> dict[str, dict[str, str]]:
    """Which model each logical role uses, per assignment config (Section 13.3).

    Built from the configured model names so changing CLOUD_MODEL /
    STRONG_MODEL / LOCAL_MODEL in .env changes every assignment that uses
    them, instead of silently keeping a hard-coded model.
    """
    s = get_settings()
    single_cloud = {role: s.cloud_model for role in ROLES}
    single_local = {role: s.local_model for role in ROLES}
    mixed = {
        "analyzer": s.local_model,
        "profiler": s.local_model,
        "compiler_exec": s.local_model,
        "benchmark": s.local_model,
        "strategist": s.strong_model,
        "transformer": s.strong_model,
        "critic": s.cloud_model,
        "manager": s.cloud_model,
    }
    for table in (single_cloud, single_local, mixed):
        table["judge"] = s.judge_model  # judge stays fixed across configs
    return {"single-cloud": single_cloud, "single-local": single_local, "mixed": mixed}


def model_for(role: str, assignment: str | None = None) -> str:
    """Resolve which model a given agent role should use."""
    cfg = get_settings()
    name = assignment or cfg.model_assignment
    tables = model_assignments()
    if name not in tables:
        raise ValueError(f"unknown model assignment {name!r}; expected one of {sorted(tables)}")
    return tables[name].get(role, cfg.cloud_model)


def price(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost of one LLM call given token usage (0 for unknown/local models)."""
    in_price, out_price = PRICE_PER_1M_TOKENS.get(model, (0.0, 0.0))
    return (prompt_tokens / 1_000_000) * in_price + (completion_tokens / 1_000_000) * out_price
