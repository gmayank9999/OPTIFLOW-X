"""Computes latency, cost and critical-path metrics from trace files.

Runs entirely over the exported trace data (results/traces/*.jsonl), so it
works the same whether the spans came from a live run or a replayed
results directory -- no dependency on OpenTelemetry's live SDK state.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd

from optiflow.observability.tracing import TRACE_DIR, trace_path


def load_spans(path: pathlib.Path) -> pd.DataFrame:
    """Load one trace file, or every *.jsonl in a directory."""
    path = pathlib.Path(path)
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    rows = []
    for f in files:
        if f.exists():
            rows.extend(json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["trace_id", "span_id", "parent_id", "name", "start", "end", "dur_ms", "attrs"])
    return df


def _agent_spans(spans: pd.DataFrame) -> pd.DataFrame:
    agent_spans = spans[spans["name"].str.startswith("agent.")].copy()
    agent_spans["agent"] = agent_spans["name"].str.replace("agent.", "", regex=False)
    return agent_spans


def per_agent_latency(spans: pd.DataFrame) -> pd.DataFrame:
    agent_spans = _agent_spans(spans)
    return (
        agent_spans.groupby("agent")["dur_ms"]
        .agg(mean="mean", median="median", p95=lambda s: s.quantile(0.95), count="count")
        .reset_index()
    )


def per_agent_tokens(spans: pd.DataFrame) -> pd.DataFrame:
    agent_spans = _agent_spans(spans)
    attrs = agent_spans["attrs"].apply(lambda a: a or {})
    agent_spans["tokens_in"] = attrs.apply(lambda a: a.get("tokens_in", 0))
    agent_spans["tokens_out"] = attrs.apply(lambda a: a.get("tokens_out", 0))
    return agent_spans.groupby("agent")[["tokens_in", "tokens_out"]].mean().reset_index()


def cost_share(spans: pd.DataFrame) -> pd.DataFrame:
    agent_spans = _agent_spans(spans)
    agent_spans["cost_usd"] = agent_spans["attrs"].apply(lambda a: (a or {}).get("cost_usd", 0.0))
    total = agent_spans["cost_usd"].sum()
    by_agent = agent_spans.groupby("agent")["cost_usd"].sum().reset_index()
    by_agent["share"] = by_agent["cost_usd"] / total if total else 0.0
    return by_agent


def critical_path(spans: pd.DataFrame, trace_id: str) -> list[dict]:
    """Walks the span tree for one trace, at each level taking the child
    that ends last, and returns that chain root-to-leaf."""
    trace_spans = spans[spans["trace_id"] == trace_id]
    by_parent: dict[str | None, list[dict]] = {}
    for _, row in trace_spans.iterrows():
        parent_id = row["parent_id"]
        parent_id = None if pd.isna(parent_id) else parent_id
        by_parent.setdefault(parent_id, []).append(row.to_dict())

    roots = by_parent.get(None, [])
    if not roots:
        return []

    path = []
    current = max(roots, key=lambda s: s["end"] or 0)
    path.append(current)
    while True:
        children = by_parent.get(current["span_id"], [])
        if not children:
            break
        current = max(children, key=lambda s: s["end"] or 0)
        path.append(current)
    return path


def critical_path_breakdown(spans: pd.DataFrame, trace_id: str) -> dict[str, float]:
    """Share of the run's wall time each agent occupies on the critical
    path. Sequential steps are all critical; when steps overlap (the
    event-driven architecture), only the one that finishes last counts."""
    trace_spans = spans[spans["trace_id"] == trace_id]
    roots = trace_spans[trace_spans["parent_id"].isna()]
    if roots.empty:
        return {}
    root = roots.iloc[0]
    children = trace_spans[(trace_spans["parent_id"] == root["span_id"]) & trace_spans["name"].str.startswith("agent.")]
    children = children.sort_values("end")
    covered_until = root["start"]
    out: dict[str, float] = {}
    for _, span in children.iterrows():
        start = max(span["start"], covered_until)
        if span["end"] > start:
            out[span["name"][6:]] = out.get(span["name"][6:], 0.0) + (span["end"] - start) / 1e6
            covered_until = span["end"]
    return out


def bottleneck_agent(path: list[dict]) -> str | None:
    agent_steps = [s for s in path if s["name"].startswith("agent.")]
    if not agent_steps:
        return None
    slowest = max(agent_steps, key=lambda s: s["dur_ms"] or 0)
    return slowest["name"].replace("agent.", "")


def critical_path_agent(run_id: str) -> str | None:
    path = trace_path(run_id)
    if not path.exists():
        return None
    spans = load_spans(path)
    if spans.empty:
        return None
    root = spans[spans["name"] == "run"]
    if root.empty:
        return None
    breakdown = critical_path_breakdown(spans, root.iloc[0]["trace_id"])
    return max(breakdown, key=breakdown.get) if breakdown else None


def agent_summary(trace_dir: pathlib.Path = TRACE_DIR, run_ids: set[str] | None = None) -> list[dict]:
    """Per-agent latency / tokens / cost table for the dashboard."""
    if run_ids is not None:
        frames = [load_spans(trace_path(r)) for r in run_ids if trace_path(r).exists()]
        spans = pd.concat(frames) if frames else load_spans(pathlib.Path("__none__"))
    else:
        spans = load_spans(trace_dir)
    if spans.empty:
        return []
    agent_spans = _agent_spans(spans)
    if agent_spans.empty:
        return []
    attrs = agent_spans["attrs"].apply(lambda a: a or {})
    agent_spans["tokens_in"] = attrs.apply(lambda a: a.get("tokens_in", 0))
    agent_spans["tokens_out"] = attrs.apply(lambda a: a.get("tokens_out", 0))
    agent_spans["cost_usd"] = attrs.apply(lambda a: a.get("cost_usd", 0.0))
    total_cost = agent_spans["cost_usd"].sum()

    crit: dict[str, float] = {}
    for trace_id in spans[spans["name"] == "run"]["trace_id"].unique():
        for agent, ms in critical_path_breakdown(spans, trace_id).items():
            crit[agent] = crit.get(agent, 0.0) + ms
    crit_total = sum(crit.values())

    out = []
    for agent, g in agent_spans.groupby("agent"):
        out.append({
            "agent": agent,
            "calls": int(len(g)),
            "mean_ms": float(g["dur_ms"].mean()),
            "median_ms": float(g["dur_ms"].median()),
            "p95_ms": float(g["dur_ms"].quantile(0.95)),
            "tokens_in_mean": float(g["tokens_in"].mean()),
            "tokens_out_mean": float(g["tokens_out"].mean()),
            "cost_usd": float(g["cost_usd"].sum()),
            "cost_share": float(g["cost_usd"].sum() / total_cost) if total_cost else 0.0,
            "critical_path_share": float(crit.get(agent, 0.0) / crit_total) if crit_total else 0.0,
        })
    order = ["analyzer", "profiler", "manager", "strategist", "transformer", "compiler_exec", "benchmark", "critic"]
    out.sort(key=lambda r: order.index(r["agent"]) if r["agent"] in order else 99)
    return out
