import pandas as pd

from optiflow.observability.metrics import critical_path, critical_path_breakdown, load_spans, per_agent_latency
from optiflow.observability.tracing import init_tracing


def test_spans_are_written_and_readable(tmp_path):
    path = tmp_path / "spans.jsonl"
    tracer = init_tracing(path)
    with tracer.start_as_current_span("run"):
        with tracer.start_as_current_span("agent.strategist", attributes={"tokens_in": 10}):
            pass
    spans = load_spans(path)
    assert set(spans["name"]) == {"run", "agent.strategist"}
    child = spans[spans["name"] == "agent.strategist"].iloc[0]
    assert child["attrs"]["tokens_in"] == 10
    assert child["parent_id"] == spans[spans["name"] == "run"].iloc[0]["span_id"]


def _span(name, span_id, parent, start, end):
    return {"trace_id": "t", "span_id": span_id, "parent_id": parent, "name": name,
            "start": start, "end": end, "dur_ms": (end - start) / 1e6, "attrs": {}}


def test_per_agent_latency_excludes_non_agent_spans():
    df = pd.DataFrame([_span("run", "r", None, 0, 10e6), _span("agent.a", "a", "r", 0, 4e6), _span("tool.x", "x", "a", 0, 1e6)])
    lat = per_agent_latency(df)
    assert list(lat["agent"]) == ["a"]


def test_critical_path_follows_last_ending_child():
    df = pd.DataFrame([
        _span("run", "r", None, 0, 10e6),
        _span("agent.a", "a", "r", 0, 3e6),
        _span("agent.b", "b", "r", 3e6, 10e6),
    ])
    assert [s["name"] for s in critical_path(df, "t")] == ["run", "agent.b"]


def test_breakdown_counts_overlapping_steps_once():
    # analyzer (0-4s) and profiler (0-6s) overlap, as in the event-driven
    # architecture; only the part of profiler not already covered counts.
    df = pd.DataFrame([
        _span("run", "r", None, 0, 10e9),
        _span("agent.analyzer", "a", "r", 0, 4e9),
        _span("agent.profiler", "p", "r", 0, 6e9),
        _span("agent.strategist", "s", "r", 6e9, 10e9),
    ])
    b = critical_path_breakdown(df, "t")
    assert round(b["analyzer"]) == 4000 and round(b["profiler"]) == 2000 and round(b["strategist"]) == 4000
    assert round(sum(b.values())) == 10000
