"""Command-line entry point.

    python -m optiflow run matmul_naive                       # one optimization run
    python -m optiflow run lcs --arch event --messaging p2p --prompt reflection
    python -m optiflow run bubble_sort --variant flags_only   # no LLM needed
    python -m optiflow programs                               # list the suite
    python -m optiflow serve                                  # API + dashboard on :8000
    python -m optiflow doctor                                 # check Docker, image, keys, KB

Experiments, stability, the sweep and analysis have their own modules;
see README.md.
"""

from __future__ import annotations

import argparse
import os
import sys


def cmd_run(args: argparse.Namespace) -> int:
    from optiflow.architectures.base import RunConfig, build

    cfg = RunConfig(
        architecture=args.arch, messaging=args.messaging, prompt_style=args.prompt,
        model_assignment=args.models, variant=args.variant, max_attempts=args.attempts,
        persona=args.persona, critic_backend=args.critic, instructions=args.instructions,
        max_usd_per_run=args.max_usd, experiment="cli",
    )

    def show(event: dict) -> None:
        t = event["type"]
        if t == "step_end":
            att = f"A{event['attempt']} " if event.get("attempt") else "   "
            cost = f"  ${event['cost_usd']:.4f}" if event.get("cost_usd") else ""
            print(f"  {att}{event['agent']:<14} {event['dur_ms'] / 1000:6.1f}s{cost}  {event.get('summary', '')[:90]}")
        elif t == "guardrail":
            print(f"  ! guardrail [{event.get('agent')}] {event.get('stage')}: {event.get('detail', '')[:80]}")
        elif t == "attempt_end":
            v = event["verdict"]
            mark = f"ACCEPT {v['speedup']:.2f}x" if v["accepted"] else f"reject: {v['reason']}"
            print(f"  -> {mark}   (best {event['best_speedup']:.2f}x)\n")

    print(f"{args.program}  [{cfg.architecture} / {cfg.messaging} / {cfg.prompt_style} / {cfg.persona} / "
          f"critic={cfg.critic_backend} / {cfg.variant}]\n")
    state = build(cfg, emit=None if args.quiet else show).run(args.program)
    best = state.best or {}
    print(f"best: {best.get('speedup', 1.0):.2f}x  ({'+'.join(best.get('strategies', [])) or 'no accepted change'})")
    print(f"stop: {state.stop_reason}   tokens: {state.usage.prompt_tokens + state.usage.completion_tokens}"
          f"   cost: ${state.usage.cost_usd:.4f}")
    print(f"saved: results/runs/{state.run_id}/")
    return 0


def cmd_programs(_: argparse.Namespace) -> int:
    import json
    import pathlib

    from optiflow.tools.registry import list_programs, load_meta

    stab = {}
    path = pathlib.Path("results/stability.json")
    if path.exists():
        stab = json.loads(path.read_text())["programs"]
    for pid in list_programs():
        meta = load_meta(pid)
        ms = stab.get(pid, {}).get("median_ms")
        print(f"{pid:24s} {meta['category']:12s} {meta['compare']:9s} "
              f"{(f'{ms:8.0f} ms' if ms else '        —'):>11s}{'  S10' if meta.get('subset10') else ''}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("optiflow.api.main:app", host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    from optiflow.core.config import get_settings

    ok = True

    def check(label: str, passed: bool, hint: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"  [{'ok' if passed else '!!'}] {label}" + ("" if passed else f"   -> {hint}"))

    try:
        from optiflow.tools.sandbox import _get_client

        client = _get_client()
        check("Docker reachable", True)
        check("sandbox image", bool(client.images.list(name=get_settings().sandbox_image)),
              "docker build -t optiflow-sandbox -f docker/sandbox.Dockerfile .")
    except Exception:  # noqa: BLE001
        check("Docker reachable", False, "start Docker Desktop")
    keys = [k for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY") if os.getenv(k)]
    check(f"LLM key ({', '.join(keys) or 'none'})", bool(keys), "add a key to .env (flags_only/rule_only work without)")
    try:
        from optiflow.knowledge.ingest import COLLECTION_NAME, get_client

        n = get_client().get_or_create_collection(COLLECTION_NAME).count()
        check(f"knowledge base ({n} chunks)", n > 0, "python -m optiflow.knowledge.ingest")
    except Exception:  # noqa: BLE001
        check("knowledge base", False, "python -m optiflow.knowledge.ingest")
    import pathlib

    check("stability table", pathlib.Path("results/stability.json").exists(),
          "python -m optiflow.experiments.stability")
    check("dashboard build", pathlib.Path("dashboard/out/index.html").exists(),
          "cd dashboard && npm install && npm run build")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    from optiflow.core.console import fix_windows_console_encoding

    fix_windows_console_encoding()
    parser = argparse.ArgumentParser(prog="python -m optiflow", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="optimize one program")
    r.add_argument("program")
    r.add_argument("--arch", default="sequential", choices=["sequential", "hierarchical", "event"])
    r.add_argument("--messaging", default="blackboard", choices=["blackboard", "p2p", "broadcast"])
    r.add_argument("--prompt", default="structured", choices=["structured", "react", "reflection", "few_shot"])
    r.add_argument("--persona", default="default",
                   choices=["default", "compiler_engineer", "hpc_researcher", "cautious_reviewer"])
    r.add_argument("--critic", default="crewai", choices=["crewai", "adk_a2a"],
                   help="adk_a2a: rejection feedback from the Google ADK reviewer over A2A")
    r.add_argument("--instructions", default="", help="optional guidance for the Strategist (screened)")
    r.add_argument("--models", default=os.getenv("MODEL_ASSIGNMENT", "single-cloud"),
                   choices=["single-cloud", "single-local", "mixed"])
    r.add_argument("--variant", default="full",
                   choices=["full", "no_rag", "no_xgb", "llm_only", "rule_only", "flags_only"])
    r.add_argument("--attempts", type=int, default=5)
    r.add_argument("--max-usd", type=float, default=0.05)
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)

    sub.add_parser("programs", help="list the benchmark suite").set_defaults(fn=cmd_programs)
    s = sub.add_parser("serve", help="API + dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    sub.add_parser("doctor", help="check the environment").set_defaults(fn=cmd_doctor)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
