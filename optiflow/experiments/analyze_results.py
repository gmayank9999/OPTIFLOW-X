"""Statistical analysis of results/runs.csv (Section 15.4) and report figures (15.5).

    python -m optiflow.experiments.analyze_results            # writes results/analysis.json + figures

- Speedup: geometric mean (the right average for ratios), median, per category.
- Success rate with a 95% Wilson interval.
- Paired comparison across configurations on the same programs: Friedman
  test, then pairwise Wilcoxon signed-rank with Holm correction.
- Cost and latency: mean / median / P95 per configuration.
- Pareto front of success rate vs mean cost.

The same functions back the dashboard's /experiments endpoints.
"""

from __future__ import annotations

import itertools
import json
import math
import pathlib

import numpy as np
import pandas as pd
from scipy.stats import friedmanchisquare, wilcoxon

from optiflow.experiments.store import RUNS_CSV

OUT_JSON = pathlib.Path("results/analysis.json")
FIG_DIR = pathlib.Path("results/figures")
ADHOC_EXPERIMENTS = frozenset({"dashboard", "cli", "smoke", "adhoc"})  # one-off runs, not designed comparisons
FACTORS =("architecture", "messaging", "prompt_style", "persona", "critic_backend", "model_config", "variant")


def load_runs(path: pathlib.Path | None = None) -> pd.DataFrame:
    path = path or RUNS_CSV
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df = df[df["error"].isna() | (df["error"] == "")] if "error" in df else df
    for col, default in (("persona", "default"), ("critic_backend", "crewai"), ("repeat", 0)):
        if col not in df:
            df[col] = default
        df[col] = df[col].fillna(default).replace("", default)
    for col in ("speedup", "cost_usd", "latency_s", "total_tokens", "success", "attempts", "messages",
                "deliveries", "message_bytes", "cpu_speedup", "guardrail_flags", "a2a_calls", "a2a_latency_ms"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    # Latest run wins when a cell was repeated by hand.
    return df.sort_values("started_at").reset_index(drop=True)


def geomean(values) -> float:
    v = np.asarray([x for x in values if x and x > 0], dtype=float)
    return float(np.exp(np.mean(np.log(v)))) if len(v) else float("nan")


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def config_label(row) -> str:
    return " / ".join(str(row[f]) for f in FACTORS)


def summarize(df: pd.DataFrame, by: str) -> list[dict]:
    out = []
    for value, g in df.groupby(by):
        n = len(g)
        s = int(g["success"].sum())
        lo, hi = wilson(s, n)
        out.append({
            by: value, "runs": n, "programs": int(g["program_id"].nunique()),
            "geomean_speedup": geomean(g["speedup"]), "median_speedup": float(g["speedup"].median()),
            "success_rate": s / n if n else float("nan"), "success_ci": [lo, hi],
            "mean_cost_usd": float(g["cost_usd"].mean()), "p95_cost_usd": float(g["cost_usd"].quantile(0.95)),
            "mean_latency_s": float(g["latency_s"].mean()), "median_latency_s": float(g["latency_s"].median()),
            "p95_latency_s": float(g["latency_s"].quantile(0.95)),
            "mean_tokens": float(g["total_tokens"].mean()), "mean_attempts": float(g["attempts"].mean()),
            "mean_messages": float(g["messages"].mean()) if "messages" in g else 0.0,
            "mean_deliveries": float(g["deliveries"].mean()) if "deliveries" in g else 0.0,
            "mean_message_bytes": float(g["message_bytes"].mean()) if "message_bytes" in g else 0.0,
        })
    return out


def paired_tests(df: pd.DataFrame, by: str) -> dict:
    """Friedman over configurations measured on the same programs, then
    Holm-corrected pairwise Wilcoxon signed-rank on log-speedups."""
    # Repeats are averaged in log space (geometric mean) per program and level.
    logged = df.assign(log_speedup=np.log(df["speedup"].clip(lower=1e-9)))
    pivot = np.exp(logged.pivot_table(index="program_id", columns=by, values="log_speedup", aggfunc="mean")).dropna()
    levels = list(pivot.columns)
    result: dict = {"factor": by, "levels": levels, "paired_programs": int(len(pivot))}
    if len(levels) < 2 or len(pivot) < 5:
        result["note"] = "need >= 2 levels measured on >= 5 common programs"
        return result
    logs = np.log(pivot.clip(lower=1e-9))
    if len(levels) >= 3:
        stat, p = friedmanchisquare(*[logs[c] for c in levels])
        result["friedman"] = {"statistic": float(stat), "p_value": float(p)}

    pairs = []
    for a, b in itertools.combinations(levels, 2):
        diff = logs[a] - logs[b]
        if np.allclose(diff, 0):
            p = 1.0
        else:
            try:
                p = float(wilcoxon(logs[a], logs[b]).pvalue)
            except ValueError:
                p = 1.0
        pairs.append({"a": a, "b": b, "p_raw": p, "median_ratio": float(np.exp(np.median(diff)))})
    # Holm step-down correction
    pairs.sort(key=lambda r: r["p_raw"])
    m = len(pairs)
    running = 0.0
    for i, r in enumerate(pairs):
        running = max(running, min(1.0, (m - i) * r["p_raw"]))
        r["p_holm"] = running
        r["significant"] = running < 0.05
    result["pairwise"] = pairs
    return result


def pareto(df: pd.DataFrame) -> list[dict]:
    points = []
    for label, g in df.groupby(df.apply(config_label, axis=1)):
        points.append({"config": label, "success_rate": float(g["success"].mean()),
                       "mean_cost_usd": float(g["cost_usd"].mean()), "runs": int(len(g)),
                       "geomean_speedup": geomean(g["speedup"])})
    for p in points:
        p["pareto"] = not any(
            q is not p and q["mean_cost_usd"] <= p["mean_cost_usd"] and q["success_rate"] >= p["success_rate"]
            and (q["mean_cost_usd"] < p["mean_cost_usd"] or q["success_rate"] > p["success_rate"])
            for q in points
        )
    return sorted(points, key=lambda p: p["mean_cost_usd"])


def per_program_best(df: pd.DataFrame) -> list[dict]:
    out = []
    for pid, g in df.groupby("program_id"):
        flags = g[g["variant"] == "flags_only"]["speedup"]
        llm = g[g["variant"].isin(["full", "no_rag", "no_xgb", "llm_only"])]
        best_llm = llm.loc[llm["speedup"].idxmax()] if not llm.empty else None
        out.append({
            "program_id": pid,
            "category": g["category"].iloc[0],
            "flags_only": float(flags.max()) if not flags.empty else None,
            "rule_only": float(g[g["variant"] == "rule_only"]["speedup"].max()) if (g["variant"] == "rule_only").any() else None,
            "best_agent": float(best_llm["speedup"]) if best_llm is not None else None,
            "best_agent_strategy": (best_llm["winning_strategy"] if best_llm is not None else None),
            "best_agent_run": (best_llm["run_id"] if best_llm is not None else None),
            "runs": int(len(g)),
        })
    return out


def analysis(df: pd.DataFrame | None = None) -> dict:
    df = load_runs() if df is None else df
    if df.empty:
        return {"runs": 0}
    by_experiment = {}
    for exp, g in df.groupby("experiment"):
        # One-off runs (dashboard, CLI, smoke tests) are not designed
        # experiments: their rows differ in program *and* configuration, so
        # any per-factor table would compare unlike things (one hand-picked
        # run against six rule-based baselines on other programs). They get
        # a single summary row and no comparisons or significance tests.
        varied = [] if exp in ADHOC_EXPERIMENTS else [f for f in FACTORS if g[f].nunique() > 1]
        by_experiment[exp] = {
            "runs": int(len(g)), "varied": varied,
            "summaries": {f: summarize(g, f) for f in varied} or {"all": summarize(g.assign(all="all"), "all")},
            "tests": {f: paired_tests(g, f) for f in varied},
        }
    return {
        "runs": int(len(df)),
        "programs": int(df["program_id"].nunique()),
        "overall_geomean_speedup": geomean(df["speedup"]),
        "total_cost_usd": float(df["cost_usd"].sum()),
        "experiments": by_experiment,
        "by_category": summarize(df, "category"),
        "pareto": pareto(df),
        "per_program": per_program_best(df),
    }


def _json_safe(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return _json_safe(float(obj))
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def json_safe(obj):
    return _json_safe(obj)


def figures(df: pd.DataFrame, result: dict) -> list[pathlib.Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    paths = []

    per = pd.DataFrame(result["per_program"])
    if not per.empty:
        per["best"] = per[["flags_only", "rule_only", "best_agent"]].max(axis=1, skipna=True)
        per = per.sort_values("best", ascending=False)
        fig, ax = plt.subplots(figsize=(10, 3.6))
        x = np.arange(len(per))
        ax.bar(x - 0.2, per["flags_only"].fillna(0), 0.4, label="flags only (-O3 -march=native)", color="#9aa4ad")
        ax.bar(x + 0.2, per["best_agent"].fillna(0), 0.4, label="best agent run", color="#1f6f5c")
        ax.axhline(1.0, color="#333", lw=0.8)
        ax.set_yscale("log")
        ax.set_xticks(x, per["program_id"], rotation=75, ha="right", fontsize=7)
        ax.set_ylabel("speedup vs -O2 (log)")
        ax.legend(frameon=False)
        fig.tight_layout()
        paths.append(FIG_DIR / "speedup_per_program.png")
        fig.savefig(paths[-1], dpi=160)
        plt.close(fig)

    pts = result["pareto"]
    if pts:
        fig, ax = plt.subplots(figsize=(5.5, 4))
        for p in pts:
            ax.scatter(p["mean_cost_usd"], p["success_rate"], s=30,
                       color="#1f6f5c" if p["pareto"] else "#9aa4ad")
        ax.set_xlabel("mean cost per run (USD)")
        ax.set_ylabel("success rate")
        fig.tight_layout()
        paths.append(FIG_DIR / "pareto.png")
        fig.savefig(paths[-1], dpi=160)
        plt.close(fig)
    return paths


def main() -> None:
    df = load_runs()
    result = json_safe(analysis(df))
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2))
    figs = figures(df, result) if not df.empty else []
    print(f"{result.get('runs', 0)} runs analysed -> {OUT_JSON}; figures: {[str(p) for p in figs]}")


if __name__ == "__main__":
    main()
