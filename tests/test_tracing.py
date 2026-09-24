import pathlib
import tempfile

from optiflow.observability import metrics
from optiflow.observability.tracing import init_tracing


def test_spans_are_written_and_readable():
    trace_path = pathlib.Path(tempfile.mkdtemp()) / "spans.jsonl"
    tracer = init_tracing(trace_path)

    with tracer.start_as_current_span("run", attributes={"program": "matmul_naive"}):
        with tracer.start_as_current_span("agent.analyzer", attributes={"attempt": 1}):
            pass
        with tracer.start_as_current_span("agent.strategist", attributes={"attempt": 1, "cost_usd": 0.001}):
            pass

    spans = metrics.load_spans(trace_path)
    assert len(spans) == 3
    assert {"agent.analyzer", "agent.strategist", "run"} <= set(spans["name"])


def test_per_agent_latency_excludes_non_agent_spans():
    trace_path = pathlib.Path(tempfile.mkdtemp()) / "spans.jsonl"
    tracer = init_tracing(trace_path)

    with tracer.start_as_current_span("run"):
        with tracer.start_as_current_span("agent.benchmark"):
            pass

    spans = metrics.load_spans(trace_path)
    latency = metrics.per_agent_latency(spans)
    assert list(latency["agent"]) == ["benchmark"]


def test_critical_path_follows_last_ending_child():
    trace_path = pathlib.Path(tempfile.mkdtemp()) / "spans.jsonl"
    tracer = init_tracing(trace_path)

    with tracer.start_as_current_span("run") as root:
        trace_id = format(root.get_span_context().trace_id, "032x")
        with tracer.start_as_current_span("agent.analyzer"):
            pass
        with tracer.start_as_current_span("agent.strategist"):
            pass

    spans = metrics.load_spans(trace_path)
    path = metrics.critical_path(spans, trace_id)
    assert path[0]["name"] == "run"
    assert metrics.bottleneck_agent(path) in {"analyzer", "strategist"}
