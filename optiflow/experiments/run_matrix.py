"""Experiment matrix runner (Section 15.2).

    python -m optiflow.experiments.run_matrix optiflow/experiments/configs/e0_baselines.yaml
    python -m optiflow.experiments.run_matrix configs/*.yaml --programs matmul_naive lcs --dry-run

Resumable: a (experiment, config, program, repeat) cell that already has
a successful row in results/runs.csv is skipped, so the matrix can run
overnight and be restarted. A failed run is logged and the matrix moves
on; it never crashes the whole sweep.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

import yaml

from optiflow.architectures.base import RunConfig, build
from optiflow.core.console import fix_windows_console_encoding
from optiflow.experiments.store import read_rows
from optiflow.tools.registry import list_programs

CONFIG_KEYS = ("architecture", "messaging", "prompt_style", "model_assignment", "variant", "persona",
               "critic_backend", "instructions", "max_attempts", "max_usd_per_run", "bench_n")


def load_config(path: pathlib.Path) -> dict:
    return yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))


def cells(config: dict, only: list[str] | None = None) -> list[tuple[RunConfig, str, int]]:
    programs = only or list_programs(subset10_only=config.get("programs") == "subset10")
    defaults = config.get("defaults", {})
    out = []
    for run in config["runs"]:
        merged = {**defaults, **run}
        for repeat in range(int(config.get("repeats", 1))):
            for pid in programs:
                cfg = RunConfig(experiment=config["name"], **{k: v for k, v in merged.items() if k in CONFIG_KEYS})
                cfg.tags = {"cell": cell_key(config["name"], merged, pid, repeat), "repeat": repeat}
                out.append((cfg, pid, repeat))
    return out


def cell_key(experiment: str, merged: dict, pid: str, repeat: int) -> str:
    sig = json.dumps({k: merged.get(k) for k in CONFIG_KEYS}, sort_keys=True)
    return hashlib.sha1(f"{experiment}|{sig}|{pid}|{repeat}".encode()).hexdigest()[:16]


def done_signatures() -> set[tuple]:
    done = set()
    for r in read_rows():
        if r.get("error"):
            continue
        done.add((r["experiment"], r["architecture"], r["messaging"], r["prompt_style"], r["model_config"],
                  r["variant"], r.get("persona") or "default", r.get("critic_backend") or "crewai",
                  r["program_id"], int(r.get("repeat") or 0)))
    return done


def main() -> None:
    fix_windows_console_encoding()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("configs", nargs="+", type=pathlib.Path)
    parser.add_argument("--programs", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in args.configs:
        config = load_config(path)
        todo = cells(config, args.programs)
        done = done_signatures()
        print(f"== {config['name']}: {len(todo)} cells", flush=True)
        for cfg, pid, repeat in todo:
            sig = (cfg.experiment, cfg.architecture, cfg.messaging, cfg.prompt_style, cfg.model_assignment,
                   cfg.variant, cfg.persona, cfg.critic_backend, pid, repeat)
            if sig in done:
                continue
            label = (f"{cfg.architecture}/{cfg.messaging}/{cfg.prompt_style}/{cfg.persona}/"
                     f"{cfg.critic_backend}/{cfg.variant}" + (f"#r{repeat}" if repeat else ""))
            if args.dry_run:
                print(f"  would run {pid:24s} {label}")
                continue
            t0 = time.time()
            try:
                state = build(cfg).run(pid)
                print(f"  {pid:24s} {label:60s} {state.best['speedup']:6.2f}x  "
                      f"{len(state.history)} att  ${state.usage.cost_usd:.4f}  {time.time() - t0:5.0f}s  "
                      f"[{state.stop_reason}]", flush=True)
            except Exception as exc:  # noqa: BLE001 - log and keep the matrix going
                print(f"  {pid:24s} {label:60s} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
