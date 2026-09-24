"""Computes latency, cost and critical-path metrics from a spans.jsonl file.

Runs entirely over the exported trace data, so it works the same whether
the spans came from a live run or a replayed results directory -- no
dependency on OpenTelemetry's live SDK state.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd


def load_spans(path: pathlib.Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return pd.DataFrame(rows)


def per_agent_latency(spans: pd.DataFrame) -> pd.DataFrame:
    agent_spans = spans[spans["name"].str.startswith("agent.")].copy()
    agent_spans["agent"] = agent_spans["name"].str.replace("agent.", "", regex=False)
    return (
        agent_spans.groupby("agent")["dur_ms"]
        .agg(mean="mean", median="median", p95=lambda s: s.quantile(0.95), count="count")
        .reset_index()
    )


def cost_share(spans: pd.DataFrame) -> pd.DataFrame:
    agent_spans = spans[spans["name"].str.startswith("agent.")].copy()
    agent_spans["agent"] = agent_spans["name"].str.replace("agent.", "", regex=False)
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


def bottleneck_agent(path: list[dict]) -> str | None:
    agent_steps = [s for s in path if s["name"].startswith("agent.")]
    if not agent_steps:
        return None
    slowest = max(agent_steps, key=lambda s: s["dur_ms"] or 0)
    return slowest["name"].replace("agent.", "")
