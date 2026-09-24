"""Environment configuration, model routing and token pricing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# USD per 1M tokens, (input, output). Local models are free but still timed.
PRICE_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "gemini/gemini-flash-lite-latest": (0.10, 0.40),
    "groq/llama-3.3-70b-versatile": (0.59, 0.79),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "ollama/qwen2.5-coder:7b": (0.0, 0.0),
}

# Which logical role uses which model, per model-assignment config.
# "single-cloud" / "single-local" / "mixed" (Section 13.3).
MODEL_ASSIGNMENTS: dict[str, dict[str, str]] = {
    "single-cloud": {
        "analyzer": "gemini/gemini-flash-lite-latest",
        "profiler": "gemini/gemini-flash-lite-latest",
        "strategist": "gemini/gemini-flash-lite-latest",
        "transformer": "gemini/gemini-flash-lite-latest",
        "compiler_exec": "gemini/gemini-flash-lite-latest",
        "benchmark": "gemini/gemini-flash-lite-latest",
        "critic": "gemini/gemini-flash-lite-latest",
    },
    "single-local": {
        "analyzer": "ollama/qwen2.5-coder:7b",
        "profiler": "ollama/qwen2.5-coder:7b",
        "strategist": "ollama/qwen2.5-coder:7b",
        "transformer": "ollama/qwen2.5-coder:7b",
        "compiler_exec": "ollama/qwen2.5-coder:7b",
        "benchmark": "ollama/qwen2.5-coder:7b",
        "critic": "ollama/qwen2.5-coder:7b",
    },
    "mixed": {
        "analyzer": "ollama/qwen2.5-coder:7b",
        "profiler": "ollama/qwen2.5-coder:7b",
        "strategist": "openai/gpt-4o-mini",
        "transformer": "openai/gpt-4o-mini",
        "compiler_exec": "ollama/qwen2.5-coder:7b",
        "benchmark": "ollama/qwen2.5-coder:7b",
        "critic": "gemini/gemini-flash-lite-latest",
    },
}


@dataclass(frozen=True)
class Settings:
    cloud_model: str
    strong_model: str
    local_model: str
    max_attempts: int
    max_usd_per_run: float
    sandbox_image: str
    sandbox_cpuset: str
    model_assignment: str = "mixed"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        cloud_model=os.getenv("CLOUD_MODEL", "gemini/gemini-flash-lite-latest"),
        strong_model=os.getenv("STRONG_MODEL", "openai/gpt-4o-mini"),
        local_model=os.getenv("LOCAL_MODEL", "ollama/qwen2.5-coder:7b"),
        max_attempts=int(os.getenv("MAX_ATTEMPTS", "5")),
        max_usd_per_run=float(os.getenv("MAX_USD_PER_RUN", "0.05")),
        sandbox_image=os.getenv("SANDBOX_IMAGE", "optiflow-sandbox"),
        sandbox_cpuset=os.getenv("SANDBOX_CPUSET", "2"),
        model_assignment=os.getenv("MODEL_ASSIGNMENT", "mixed"),
    )


def model_for(role: str, assignment: str | None = None) -> str:
    """Resolve which model a given agent role should use."""
    cfg = get_settings()
    table = MODEL_ASSIGNMENTS.get(assignment or cfg.model_assignment, MODEL_ASSIGNMENTS["mixed"])
    return table.get(role, cfg.cloud_model)


def price(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost of one LLM call given token usage."""
    in_price, out_price = PRICE_PER_1M_TOKENS.get(model, (0.0, 0.0))
    return (prompt_tokens / 1_000_000) * in_price + (completion_tokens / 1_000_000) * out_price
