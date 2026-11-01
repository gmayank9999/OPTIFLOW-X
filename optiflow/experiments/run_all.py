"""Run the LLM experiments in priority order. Resumable; safe to re-run.

    python -m optiflow.experiments.run_all                  # everything that is left
    python -m optiflow.experiments.run_all --only e6_interop e3_prompting
    python -m optiflow.experiments.run_all --dry-run        # list the cells that would run

Order follows importance to the course requirements:
  E6 (CrewAI vs ADK over A2A) -> E3 (prompt + persona variance) -> E2 (messaging)
  -> E5 (ablations) -> E7 (architecture, 3 repeats per cell).

The LLM provider's daily quota is shared by every experiment, so a quota stop
(run_matrix exits with code 3) ends the whole run. Start it again later: cells
that already have a result are skipped. Each experiment gets a second pass to
re-run cells lost to a transient failure, and results/analysis.json is
refreshed after each experiment.

E4 (local / mixed model assignment) is deliberately not in the list: it needs a
local 7B model (about 5 GB of RAM, which would distort the timings on a laptop)
and an OpenAI key.
"""

from __future__ import annotations

import argparse
import atexit
import os
import pathlib
import subprocess
import sys
import time
from typing import Callable

CONFIG_DIR = pathlib.Path(__file__).parent / "configs"
ORDER = ("e6_interop", "e3_prompting", "e2_messaging", "e5_ablations", "e7_repeats")
QUOTA_EXIT = 3
LOCK = pathlib.Path("results/.run_all.lock")


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode


def run_all(only: list[str] | None = None, dry_run: bool = False,
            runner: Callable[[list[str]], int] = _run, passes: int = 2) -> int:
    unknown = set(only or ()) - set(ORDER)
    if unknown:
        raise SystemExit(f"unknown experiment(s): {sorted(unknown)}; choose from {list(ORDER)}")
    py = [sys.executable, "-u", "-m"]
    for name in [n for n in ORDER if not only or n in only]:
        for attempt in range(1, (1 if dry_run else passes) + 1):
            print(f"=== {time.strftime('%H:%M:%S')} {name} (pass {attempt})", flush=True)
            cmd = [*py, "optiflow.experiments.run_matrix", str(CONFIG_DIR / f"{name}.yaml")]
            code = runner(cmd + (["--dry-run"] if dry_run else []))
            if code == QUOTA_EXIT:
                print(f"=== QUOTA-STOP during {name}: the LLM provider's daily quota is used up. "
                      "Run this command again later to resume where it stopped.", flush=True)
                return QUOTA_EXIT
        if not dry_run:
            runner([*py, "optiflow.experiments.analyze_results"])
    print(f"=== {time.strftime('%H:%M:%S')} ALL DONE", flush=True)
    return 0


def _acquire_lock() -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(
            f"{LOCK} exists: another experiment run is probably active. Two runs at once would "
            "distort each other's timings. If none is running, delete that file and retry."
        )
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    atexit.register(lambda: LOCK.unlink(missing_ok=True))


def main() -> None:
    from optiflow.core.console import fix_windows_console_encoding

    fix_windows_console_encoding()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="*", help=f"subset of: {', '.join(ORDER)}")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        _acquire_lock()
    sys.exit(run_all(args.only, args.dry_run))


if __name__ == "__main__":
    main()
