"""LLM judge for Strategist plans (Section 14.4).

A separate model (JUDGE_MODEL; ideally a different family from the
Strategist's, to limit self-preference bias) scores each plan 1-5 on:
relevance to the profiled bottleneck, technical correctness,
attributability, and use of feedback, with a fixed rubric and three
scored examples.

    python -m optiflow.observability.judge score             # score every unscored plan
    python -m optiflow.observability.judge export-human 30   # CSV for hand scoring
    python -m optiflow.observability.judge validate human.csv  # Spearman judge vs human

Scores go to results/judge_scores.jsonl; the dashboard and the
analysis join them to runs by run_id.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import random
import re

from scipy.stats import spearmanr

from optiflow.experiments.store import RUNS_DIR, load_report

SCORES_PATH = pathlib.Path("results/judge_scores.jsonl")
DIMENSIONS = ("relevance", "correctness", "attributability", "feedback_use")

RUBRIC = """\
You are grading an optimization plan written by another model for a C program.
Score each dimension from 1 (poor) to 5 (excellent):
- relevance: does it target where the profile says the time goes (hotspot lines, miss rates)?
- correctness: is the proposed transformation technically sound and likely to preserve output?
- attributability: few enough changes at once that the effect can be attributed (1-2 strategies is ideal)?
- feedback_use: does it learn from previous attempts (no repeating a failure; builds on successes)?
  Use 3 if there were no previous attempts.

EXAMPLES
1. Profile: 99% in a triple loop, L1 miss 57%, stride mismatch. Plan: interchange i-k-j + -O3.
   -> {"relevance": 5, "correctness": 5, "attributability": 5, "feedback_use": 3}
2. Profile: 99% in a recursive fib(). Plan: tiling + vectorize + unroll + -ffast-math.
   -> {"relevance": 1, "correctness": 2, "attributability": 1, "feedback_use": 3}
3. Previous: A1 tiling -> REJECT wrong_output on n=33. Plan: tiling again with min() bounds on remainders.
   -> {"relevance": 4, "correctness": 4, "attributability": 5, "feedback_use": 5}

Return ONLY JSON: {"relevance": n, "correctness": n, "attributability": n, "feedback_use": n, "comment": "<one sentence>"}
"""


def iter_plans(run_ids: list[str] | None = None):
    run_dirs = [RUNS_DIR / r for r in run_ids] if run_ids else sorted(RUNS_DIR.glob("*"))
    for run_dir in run_dirs:
        report = load_report(run_dir.name)
        if not report:
            continue
        state = report["state"]
        if state.get("variant") in ("rule_only", "flags_only"):
            continue
        profile = state.get("profile") or {}
        previous = []
        for h in state.get("history", []):
            if h.get("plan"):
                yield {
                    "run_id": state["run_id"], "attempt": h["attempt"], "program_id": state["program_id"],
                    "profile": {k: profile.get(k) for k in ("bottleneck_text", "hotspots", "l1_miss_rate", "ipc")},
                    "previous": list(previous), "plan": h["plan"],
                }
            v = h["verdict"]
            names = "+".join(s["name"] for s in (h.get("plan") or {}).get("strategies", []))
            previous.append(f"A{h['attempt']} {names} -> {'ACCEPT' if v['accepted'] else 'REJECT ' + v['reason']}")


def _scored_keys() -> set[tuple[str, int]]:
    if not SCORES_PATH.exists():
        return set()
    return {(r["run_id"], r["attempt"]) for r in map(json.loads, SCORES_PATH.read_text().splitlines()) if r}


def judge_plan(agent, item: dict) -> dict:
    from optiflow.core import llm

    prompt = (f"{RUBRIC}\nPROGRAM: {item['program_id']}\nPROFILE: {json.dumps(item['profile'])}\n"
              f"PREVIOUS ATTEMPTS: {item['previous'] or '(none)'}\nPLAN: {json.dumps(item['plan'])}")
    text, usage = llm.call(agent, prompt, "JSON scores")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(m.group(0)) if m else {}
    scores = {d: int(min(5, max(1, int(data.get(d, 3))))) for d in DIMENSIONS}
    return {
        "run_id": item["run_id"], "attempt": item["attempt"], "program_id": item["program_id"],
        **scores, "mean": sum(scores.values()) / len(scores),
        "comment": str(data.get("comment", ""))[:300], "cost_usd": usage.cost_usd,
    }


def score_all(run_ids: list[str] | None = None) -> int:
    from optiflow.agents.common import make_agent

    agent = make_agent("judge", title="Plan Judge", goal="Grade optimization plans fairly against a rubric.",
                       backstory="You are a strict, consistent reviewer of performance-engineering plans.",
                       assignment=None, temperature=0.0)
    done = _scored_keys()
    n = 0
    SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    for item in iter_plans(run_ids):
        if (item["run_id"], item["attempt"]) in done:
            continue
        record = judge_plan(agent, item)
        with open(SCORES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        n += 1
    return n


def load_scores() -> list[dict]:
    if not SCORES_PATH.exists():
        return []
    return [json.loads(line) for line in SCORES_PATH.read_text().splitlines() if line.strip()]


def export_human(k: int, path: pathlib.Path = pathlib.Path("results/judge_human_sample.csv")) -> pathlib.Path:
    items = list(iter_plans())
    random.Random(7).shuffle(items)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "attempt", "program_id", "profile", "previous", "plan", *DIMENSIONS])
        for it in items[:k]:
            w.writerow([it["run_id"], it["attempt"], it["program_id"], json.dumps(it["profile"]),
                        " | ".join(it["previous"]), json.dumps(it["plan"]), "", "", "", ""])
    return path


def validate(human_csv: pathlib.Path) -> dict:
    judge = {(r["run_id"], int(r["attempt"])): r for r in load_scores()}
    pairs = []
    with open(human_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["run_id"], int(row["attempt"]))
            if key in judge and all(row.get(d) for d in DIMENSIONS):
                human_mean = sum(float(row[d]) for d in DIMENSIONS) / len(DIMENSIONS)
                pairs.append((human_mean, judge[key]["mean"]))
    if len(pairs) < 5:
        return {"pairs": len(pairs), "note": "need >= 5 hand-scored plans that the judge also scored"}
    rho, p = spearmanr([a for a, _ in pairs], [b for _, b in pairs])
    return {"pairs": len(pairs), "spearman_rho": float(rho), "p_value": float(p)}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--runs", nargs="*")
    e = sub.add_parser("export-human")
    e.add_argument("k", type=int, nargs="?", default=30)
    v = sub.add_parser("validate")
    v.add_argument("csv", type=pathlib.Path)
    args = parser.parse_args()
    if args.cmd == "score":
        print(f"scored {score_all(args.runs)} plans -> {SCORES_PATH}")
    elif args.cmd == "export-human":
        print(f"wrote {export_human(args.k)}")
    else:
        print(json.dumps(validate(args.csv), indent=2))


if __name__ == "__main__":
    main()
