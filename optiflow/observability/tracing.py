"""OpenTelemetry tracing with a JSONL file exporter.

Every agent call and tool call becomes a span. Spans are appended to
results/traces/spans.jsonl so metrics.py can reconstruct latency, cost and
the critical path after the fact without a running collector.

Tracers come from a locally held TracerProvider rather than the global
opentelemetry.trace API, since the global provider can only be set once
per process -- that would make init_tracing() impossible to point at a
different file within the same test run.
"""

from __future__ import annotations

import json
import pathlib
import threading

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Tracer

DEFAULT_TRACE_PATH = pathlib.Path("results/traces/spans.jsonl")

_lock = threading.Lock()
_provider: TracerProvider | None = None
_provider_path: pathlib.Path | None = None


class JsonlExporter(SpanExporter):
    def __init__(self, path: pathlib.Path = DEFAULT_TRACE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    def export(self, spans) -> SpanExportResult:
        with _lock, open(self._path, "a", encoding="utf-8") as f:
            for span in spans:
                f.write(json.dumps(_span_to_dict(span)) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def _span_to_dict(span) -> dict:
    ctx = span.get_span_context()
    parent = span.parent
    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        "parent_id": format(parent.span_id, "016x") if parent else None,
        "name": span.name,
        "start": span.start_time,
        "end": span.end_time,
        "dur_ms": (span.end_time - span.start_time) / 1e6 if span.end_time else None,
        "attrs": dict(span.attributes or {}),
    }


def init_tracing(path: pathlib.Path = DEFAULT_TRACE_PATH) -> Tracer:
    """Idempotent for a given path: returns the same tracer on repeated
    calls, but a new path builds a fresh provider (mainly for tests)."""
    global _provider, _provider_path
    if _provider is None or _provider_path != path:
        _provider = TracerProvider()
        _provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(path)))
        _provider_path = path
    return _provider.get_tracer("optiflow")


def get_tracer() -> Tracer:
    return init_tracing()
