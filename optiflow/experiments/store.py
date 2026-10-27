"""Run persistence (Section 10.3 / 15.3).

Each finished run writes:
  results/runs/<run_id>/report.json   full RunState + config
  results/runs/<run_id>/best.c        best accepted source (or the original)
  results/runs/<run_id>/diff.patch    original -> best
  results/runs/<run_id>/events.jsonl  the step/attempt event stream
and appends one row to results/runs.csv. Judged LLM attempts are also
appended to results/experience.jsonl, the cross-run memory the XGBoost
dataset builder learns from.
"""

from __future__ import annotations

import csv
import json
import pathlib
import threading

from optiflow.agents.codeblock import unified_diff
from optiflow.core.schemas import RunState

RESULTS = pathlib.Path("results")
RUNS_DIR = RESULTS / "runs"
RUNS_CSV = RESULTS / "runs.csv"
EXPERIENCE = RESULTS / "experience.jsonl"

CSV_COLUMNS = [
    "run_id", "experiment", "program_id", "category", "architecture", "messaging", "prompt_style",
    "model_config", "variant", "success", "speedup", "cpu_speedup", "baseline_ms", "best_ms",
    "peak_mem_delta_kb", "attempts", "attempts_to_best", "compile_fail", "wrong_output",
    "sanitizer_fail", "total_tokens", "cost_usd", "latency_s", "crit_path_agent", "judge_score_mean",
    "winning_strategy", "stop_reason", "messages", "deliveries", "message_bytes", "error",
    "started_at",
]

_lock = threading.Lock()


def save_run(state: RunState, cfg, events: list[dict]) -> pathlib.Path:
    run_dir = RUNS_DIR / state.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    original = state.summary.source if state.summary else ""
    best_source = (state.best or {}).get("candidate", {}).get("source") or original
    ext = "cpp" if state.summary and state.summary.language == "cpp" else "c"

    report = {
        "config": {k: v for k, v in cfg.__dict__.items()},
        "state": state.model_dump(),
        "row": row_from(state, cfg),
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (run_dir / f"best.{ext}").write_text(best_source, encoding="utf-8")
    (run_dir / "diff.patch").write_text(unified_diff(original, best_source, f"main.{ext}"), encoding="utf-8")
    with open(run_dir / "events.jsonl", "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")
    append_csv(report["row"])
    return run_dir


def row_from(state: RunState, cfg) -> dict:
    from optiflow.observability.metrics import critical_path_agent
    from optiflow.tools.registry import load_meta

    history = state.history
    best = state.best or {}
    compare = best.get("compare") or {}
    base = compare.get("baseline") or {}
    cand = compare.get("candidate") or {}
    reasons = [h["verdict"]["reason"] for h in history]
    try:
        category = load_meta(state.program_id).get("category", "")
    except KeyError:
        category = ""
    speedup = float(best.get("speedup", 1.0))
    return {
        "run_id": state.run_id,
        "experiment": getattr(cfg, "experiment", "adhoc"),
        "program_id": state.program_id,
        "category": category,
        "architecture": state.architecture,
        "messaging": state.messaging,
        "prompt_style": state.prompt_style,
        "model_config": state.model_assignment,
        "variant": state.variant,
        "success": int(speedup >= 1.05 and best.get("attempt", 0) > 0),
        "speedup": round(speedup, 4),
        "cpu_speedup": round(float(compare.get("cpu_speedup", 1.0) or 1.0), 4),
        "baseline_ms": round(base.get("median_ms", state.profile.baseline_runtime_ms if state.profile else 0.0), 3),
        "best_ms": round(cand.get("median_ms", base.get("median_ms", 0.0)), 3),
        "peak_mem_delta_kb": int(cand.get("peak_mem_kb", 0) - base.get("peak_mem_kb", 0)) if cand else 0,
        "attempts": len(history),
        "attempts_to_best": int(best.get("attempt", 0)),
        "compile_fail": reasons.count("compile_error"),
        "wrong_output": reasons.count("wrong_output"),
        "sanitizer_fail": reasons.count("sanitizer_error"),
        "total_tokens": state.usage.prompt_tokens + state.usage.completion_tokens,
        "cost_usd": round(state.usage.cost_usd, 6),
        "latency_s": round(max(0.0, state.finished_at - state.started_at), 2),
        "crit_path_agent": critical_path_agent(state.run_id) or "",
        "judge_score_mean": "",
        "winning_strategy": "+".join(best.get("strategies", [])),
        "stop_reason": state.stop_reason,
        "messages": state.messaging_stats.get("messages", 0),
        "deliveries": state.messaging_stats.get("deliveries", 0),
        "message_bytes": state.messaging_stats.get("bytes", 0),
        "error": (state.error or "").splitlines()[0][:200] if state.error else "",
        "started_at": round(state.started_at, 1),
    }


def append_csv(row: dict, path: pathlib.Path | None = None) -> None:
    # Resolved at call time (not as a default argument) so tests and tools
    # that redirect RUNS_CSV actually take effect.
    path = path or RUNS_CSV
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            if new:
                writer.writeheader()
            writer.writerow(row)


def read_rows(path: pathlib.Path | None = None) -> list[dict]:
    path = path or RUNS_CSV
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_experience(record: dict) -> None:
    with _lock:
        EXPERIENCE.parent.mkdir(parents=True, exist_ok=True)
        with open(EXPERIENCE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def load_report(run_id: str) -> dict | None:
    path = RUNS_DIR / run_id / "report.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_events(run_id: str) -> list[dict]:
    path = RUNS_DIR / run_id / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
