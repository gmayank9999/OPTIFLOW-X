"""Loads benchmark programs (source + metadata) from benchmarks/."""

from __future__ import annotations

import json
import pathlib

BENCHMARKS_ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks"
# Programs pasted or uploaded through the workspace. Kept apart from the
# benchmark suite so the manifest, the stability table and the experiment
# matrix never see them (see optiflow/tools/custom.py).
CUSTOM_ROOT = pathlib.Path(__file__).resolve().parents[2] / "results" / "custom_programs"
CUSTOM_PREFIX = "custom_"


def is_custom(program_id: str) -> bool:
    return program_id.startswith(CUSTOM_PREFIX)


def _program_dir(program_id: str) -> pathlib.Path:
    d = (CUSTOM_ROOT if is_custom(program_id) else BENCHMARKS_ROOT) / program_id
    if not d.is_dir():
        raise KeyError(f"unknown program_id: {program_id}")
    return d


def load_meta(program_id: str) -> dict:
    d = _program_dir(program_id)
    return json.loads((d / "meta.json").read_text())


def load(program_id: str) -> dict:
    d = _program_dir(program_id)
    meta = load_meta(program_id)
    src_name = "main.c" if meta["language"] == "c" else "main.cpp"
    source = (d / src_name).read_text()
    return {"program_id": program_id, "source": source, "meta": meta}


def input_path(program_id: str, relative: str) -> str:
    return str(_program_dir(program_id) / relative)


def expected_path(program_id: str, relative: str) -> str:
    return str(_program_dir(program_id) / relative)


def list_programs(subset10_only: bool = False) -> list[str]:
    manifest = json.loads((BENCHMARKS_ROOT / "manifest.json").read_text())
    ids = [p["id"] for p in manifest["programs"]]
    if subset10_only:
        ids = [pid for pid in ids if load_meta(pid).get("subset10")]
    return ids
