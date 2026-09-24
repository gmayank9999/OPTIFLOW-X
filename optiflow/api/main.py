"""FastAPI backend: starts runs, streams live agent steps, serves reports
and aggregated experiment metrics to the dashboard."""

from __future__ import annotations

import asyncio
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from optiflow.architectures.base import RunConfig
from optiflow.core.console import fix_windows_console_encoding
from optiflow.tools.registry import list_programs, load_meta

fix_windows_console_encoding()

app = FastAPI(title="OPTIFLOW-X API")

# run_id -> {"status": ..., "state": RunState | None, "error": str | None}
_runs: dict[str, dict] = {}
_subscribers: dict[str, list[WebSocket]] = {}


class StartRunRequest(BaseModel):
    program_id: str
    architecture: Literal["sequential", "hierarchical", "event"] = "sequential"
    messaging: Literal["blackboard", "p2p", "broadcast"] = "blackboard"
    prompt_style: Literal["structured", "react", "reflection"] = "structured"
    model_assignment: Literal["single-cloud", "single-local", "mixed"] = "mixed"
    max_attempts: int = 5


@app.get("/programs")
def get_programs() -> list[dict]:
    return [{"id": pid, **load_meta(pid)} for pid in list_programs()]


@app.post("/runs")
def start_run(req: StartRunRequest) -> dict:
    if req.program_id not in list_programs():
        raise HTTPException(status_code=404, detail=f"unknown program: {req.program_id}")

    run_id = uuid.uuid4().hex
    _runs[run_id] = {"status": "queued", "state": None, "error": None}
    asyncio.create_task(_execute_run(run_id, req))
    return {"run_id": run_id, "status": "queued"}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    entry = _runs.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    state = entry["state"]
    return {
        "run_id": run_id,
        "status": entry["status"],
        "error": entry["error"],
        "history": state.history if state else [],
        "best": state.best if state else None,
    }


@app.websocket("/runs/{run_id}/stream")
async def stream_run(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    _subscribers.setdefault(run_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _subscribers[run_id].remove(websocket)


async def _execute_run(run_id: str, req: StartRunRequest) -> None:
    from optiflow.architectures.sequential import Sequential
    from optiflow.comms.blackboard import Blackboard
    from optiflow.comms.broadcast import Broadcast
    from optiflow.comms.p2p import PeerToPeer

    _runs[run_id]["status"] = "running"
    try:
        channel = {"blackboard": Blackboard, "p2p": PeerToPeer, "broadcast": Broadcast}[req.messaging]()
        cfg = RunConfig(
            architecture=req.architecture,
            messaging=req.messaging,
            prompt_style=req.prompt_style,
            model_assignment=req.model_assignment,
            max_attempts=req.max_attempts,
        )
        arch = {"sequential": Sequential}[req.architecture](channel, cfg)
        state = await asyncio.to_thread(arch.run, req.program_id)
        _runs[run_id]["state"] = state
        _runs[run_id]["status"] = "done"
    except Exception as exc:  # noqa: BLE001 - surfaced to the dashboard, not swallowed
        _runs[run_id]["status"] = "failed"
        _runs[run_id]["error"] = str(exc)
