"""FastAPI backend: starts runs, streams live agent steps, serves reports
and aggregated experiment metrics to the dashboard.

Runs execute one at a time on a single worker thread. That's deliberate:
every benchmark is pinned to the same CPU core, so two concurrent runs
would contaminate each other's timings. Queued runs wait their turn.

    uvicorn optiflow.api.main:app --port 8000

If the dashboard has been built (`npm run build` in dashboard/), its
static export is served at / as well.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import queue
import threading
import time
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from optiflow.architectures.base import RunConfig
from optiflow.core.console import fix_windows_console_encoding
from optiflow.experiments.store import RUNS_DIR, load_events, load_report, read_rows
from optiflow.tools.registry import _program_dir, list_programs, load, load_meta

fix_windows_console_encoding()

@contextlib.asynccontextmanager
async def _lifespan(_app):
    global _loop
    _loop = asyncio.get_running_loop()  # worker thread pushes events onto it
    yield


app = FastAPI(title="OPTIFLOW-X API", version="1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RESULTS = pathlib.Path("results")
DASHBOARD_OUT = pathlib.Path("dashboard/out")

# run_id -> {"status", "config", "program_id", "events": [...], "error", "queued_at", ...}
_runs: dict[str, dict] = {}
_subscribers: dict[str, list[asyncio.Queue]] = {}
_queue: "queue.Queue[tuple[str, RunConfig, str]]" = queue.Queue()
_loop: asyncio.AbstractEventLoop | None = None
_worker: threading.Thread | None = None
_lock = threading.Lock()


class StartRunRequest(BaseModel):
    program_id: str
    architecture: Literal["sequential", "hierarchical", "event"] = "sequential"
    messaging: Literal["blackboard", "p2p", "broadcast"] = "blackboard"
    prompt_style: Literal["structured", "react", "reflection"] = "structured"
    model_assignment: Literal["single-cloud", "single-local", "mixed"] = "single-cloud"
    variant: Literal["full", "no_rag", "no_xgb", "llm_only", "rule_only", "flags_only"] = "full"
    max_attempts: int = Field(5, ge=1, le=10)


# --------------------------------------------------------------- run worker

def _publish(run_id: str, event: dict) -> None:
    with _lock:
        entry = _runs.get(run_id)
        if entry is not None:
            entry["events"].append(event)
            if event["type"] == "run_start":
                entry["status"] = "running"
    if _loop is None:
        return
    for q in list(_subscribers.get(run_id, [])):
        _loop.call_soon_threadsafe(q.put_nowait, event)


def _worker_main() -> None:
    from optiflow.architectures.base import build

    while True:
        run_id, cfg, program_id = _queue.get()
        with _lock:
            _runs[run_id]["status"] = "running"
            _runs[run_id]["started_at"] = time.time()
        try:
            state = build(cfg, emit=lambda e, rid=run_id: _publish(rid, e)).run(program_id)
            with _lock:
                _runs[run_id]["status"] = "done"
                _runs[run_id]["best_speedup"] = state.best["speedup"] if state.best else 1.0
        except Exception as exc:  # noqa: BLE001 - surfaced to the dashboard, not swallowed
            with _lock:
                _runs[run_id]["status"] = "failed"
                _runs[run_id]["error"] = f"{type(exc).__name__}: {exc}"
            _publish(run_id, {"type": "run_end", "status": "failed", "error": str(exc), "t": time.time(),
                              "run_id": run_id})
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_worker_main, name="optiflow-run-worker", daemon=True)
        _worker.start()


# ---------------------------------------------------------------- endpoints

@app.get("/api/health")
def health() -> dict:
    from optiflow.core.config import get_settings, model_assignments

    docker_ok, image_ok = False, False
    try:
        from optiflow.tools.sandbox import _get_client

        client = _get_client()
        docker_ok = True
        image_ok = bool(client.images.list(name=get_settings().sandbox_image))
    except Exception:  # noqa: BLE001
        pass
    s = get_settings()
    keys = {k: bool(os.getenv(k)) for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY")}
    return {
        "docker": docker_ok, "sandbox_image": image_ok, "keys": keys,
        "model_assignment": s.model_assignment, "assignments": model_assignments(),
        "machine": _read_json(RESULTS / "machine.json"),
        "queue_depth": _queue.qsize(),
        "active_run": next((rid for rid, r in _runs.items() if r["status"] == "running"), None),
    }


@app.get("/api/programs")
def get_programs() -> list[dict]:
    stability = (_read_json(RESULTS / "stability.json") or {}).get("programs", {})
    best = _best_by_program()
    out = []
    for pid in list_programs():
        meta = load_meta(pid)
        stab = stability.get(pid, {})
        out.append({
            "id": pid, "category": meta.get("category"), "language": meta.get("language"),
            "compare": meta.get("compare"), "subset10": bool(meta.get("subset10")),
            "baseline_ms": stab.get("median_ms"), "cv": stab.get("cv_within_max"),
            "cv_across": stab.get("cv_across_sessions"),
            **best.get(pid, {}),
        })
    return out


@app.get("/api/programs/{program_id}")
def get_program(program_id: str) -> dict:
    if program_id not in list_programs():
        raise HTTPException(404, f"unknown program: {program_id}")
    from optiflow.tools import analyze

    program = load(program_id)
    analysis = analyze.analyze(program["source"], program["meta"]["language"])
    profile = _read_json(RESULTS / "profiles" / f"{program_id}.json")
    inputs = []
    for rel in program["meta"]["inputs"]:
        path = _program_dir(program_id) / rel
        head = path.read_text()[:160]
        inputs.append({"name": rel, "bytes": path.stat().st_size, "head": head})
    sweep = next((d for d in (_read_json(RESULTS / "ml_sweep_detail.json") or []) if d["program_id"] == program_id), None)
    runs = [r for r in read_rows() if r["program_id"] == program_id]
    return {
        "id": program_id, "meta": program["meta"], "source": program["source"],
        "functions": analysis["functions"], "loops": analysis["loops"], "features": analysis["features"],
        "profile": (profile or {}).get("report"), "inputs": inputs, "sweep": sweep,
        "stability": (_read_json(RESULTS / "stability.json") or {}).get("programs", {}).get(program_id),
        "runs": sorted(runs, key=lambda r: float(r.get("started_at") or 0), reverse=True),
    }


@app.post("/api/runs")
def start_run(req: StartRunRequest) -> dict:
    if req.program_id not in list_programs():
        raise HTTPException(status_code=404, detail=f"unknown program: {req.program_id}")
    run_id = uuid.uuid4().hex
    cfg = RunConfig(
        architecture=req.architecture, messaging=req.messaging, prompt_style=req.prompt_style,
        model_assignment=req.model_assignment, variant=req.variant, max_attempts=req.max_attempts,
        experiment="dashboard", run_id=run_id,
    )
    with _lock:
        _runs[run_id] = {"status": "queued", "program_id": req.program_id, "config": req.model_dump(),
                         "events": [], "error": None, "queued_at": time.time()}
    _ensure_worker()
    _queue.put((run_id, cfg, req.program_id))
    return {"run_id": run_id, "status": "queued", "position": _queue.qsize()}


@app.get("/api/runs")
def list_runs(limit: int = 200) -> list[dict]:
    rows = {r["run_id"]: {**r, "status": "failed" if r.get("error") else "done"} for r in read_rows()}
    with _lock:
        for rid, r in _runs.items():
            if r["status"] in ("queued", "running"):
                rows[rid] = {"run_id": rid, "program_id": r["program_id"], "status": r["status"],
                             "started_at": r.get("started_at") or r["queued_at"], **r["config"]}
    ordered = sorted(rows.values(), key=lambda r: float(r.get("started_at") or 0), reverse=True)
    return ordered[:limit]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    with _lock:
        live = _runs.get(run_id)
        live_copy = dict(live) if live else None
    report = load_report(run_id)
    if live_copy is None and report is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    if report is not None:
        state = report["state"]
        return {
            "run_id": run_id, "status": "failed" if state.get("error") else "done",
            "program_id": state["program_id"], "config": report["config"], "row": report["row"],
            "state": state, "events": load_events(run_id),
            "original_source": (state.get("summary") or {}).get("source", ""),
        }
    return {
        "run_id": run_id, "status": live_copy["status"], "program_id": live_copy["program_id"],
        "config": live_copy["config"], "events": live_copy["events"], "error": live_copy["error"],
        "original_source": load(live_copy["program_id"])["source"],
    }


@app.websocket("/api/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    with _lock:
        backlog = list(_runs[run_id]["events"]) if run_id in _runs else load_events(run_id)
        _subscribers.setdefault(run_id, []).append(q)
    try:
        for event in backlog:
            await websocket.send_text(json.dumps(event, default=str))
        if backlog and backlog[-1].get("type") == "run_end":
            return
        while True:
            event = await q.get()
            await websocket.send_text(json.dumps(event, default=str))
            if event.get("type") == "run_end":
                break
    except WebSocketDisconnect:
        pass
    finally:
        with _lock:
            if q in _subscribers.get(run_id, []):
                _subscribers[run_id].remove(q)
        try:
            await websocket.close()
        except RuntimeError:
            pass


@app.get("/api/metrics/agents")
def agent_metrics(architecture: str | None = None, experiment: str | None = None) -> list[dict]:
    from optiflow.observability.metrics import agent_summary

    rows = read_rows()
    if architecture or experiment:
        ids = {r["run_id"] for r in rows
               if (not architecture or r["architecture"] == architecture)
               and (not experiment or r["experiment"] == experiment)}
        return agent_summary(run_ids=ids)
    return agent_summary(run_ids={r["run_id"] for r in rows})


@app.get("/api/experiments/summary")
def experiments_summary() -> dict:
    from optiflow.experiments.analyze_results import analysis, json_safe

    return json_safe(analysis())


@app.get("/api/ml")
def ml_report() -> dict:
    from optiflow.ml.predictor import backends

    dataset = []
    path = RESULTS / "ml_dataset.csv"
    if path.exists():
        import csv

        with open(path, newline="", encoding="utf-8") as f:
            dataset = list(csv.DictReader(f))
    return {"report": _read_json(RESULTS / "xgb_report.json"), "backends": backends(), "dataset": dataset}


@app.get("/api/stability")
def stability() -> dict:
    return {"stability": _read_json(RESULTS / "stability.json"), "machine": _read_json(RESULTS / "machine.json")}


@app.get("/api/judge")
def judge_scores() -> list[dict]:
    from optiflow.observability.judge import load_scores

    return load_scores()


# ------------------------------------------------------------------ helpers

def _read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _best_by_program() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in read_rows():
        if r.get("error"):
            continue
        pid = r["program_id"]
        entry = out.setdefault(pid, {"runs": 0, "best_speedup": None, "flags_speedup": None,
                                     "best_strategy": None, "best_run": None})
        entry["runs"] += 1
        sp = float(r.get("speedup") or 0)
        if r["variant"] == "flags_only":
            entry["flags_speedup"] = max(entry["flags_speedup"] or 0, sp)
        elif r["variant"] != "rule_only" and sp > (entry["best_speedup"] or 0):
            entry["best_speedup"] = sp
            entry["best_strategy"] = r.get("winning_strategy")
            entry["best_run"] = r["run_id"]
    return out


if DASHBOARD_OUT.is_dir():
    app.mount("/", StaticFiles(directory=DASHBOARD_OUT, html=True), name="dashboard")
