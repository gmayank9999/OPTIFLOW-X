"""OpenTelemetry tracing with a JSONL file exporter.

Every agent step and every MCP tool call becomes a span, with model,
token and cost attributes on agent spans. Each run writes its own file,
results/traces/<run_id>.jsonl (Section 10.3), so metrics.py can
reconstruct latency, cost and the critical path after the fact without a
running collector.

Tracers come from locally held TracerProviders rather than the global
opentelemetry.trace API, since the global provider can only be set once
per process -- that would make per-run trace files impossible.
"""

from __future__ import annotations

import json
import pathlib
import threading

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Tracer

TRACE_DIR = pathlib.Path("results/traces")
DEFAULT_TRACE_PATH = TRACE_DIR / "spans.jsonl"

_lock = threading.Lock()
_providers: dict[pathlib.Path, TracerProvider] = {}


class JsonlExporter(SpanExporter):
    def __init__(self, path: pathlib.Path = DEFAULT_TRACE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path

    def export(self, spans) -> SpanExportResult:
        with _lock, open(self._path, "a", encoding="utf-8") as f:
            for span in spans:
                f.write(json.dumps(_span_to_dict(span), default=str) + "\n")
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
        "status": span.status.status_code.name if span.status else "UNSET",
        "attrs": dict(span.attributes or {}),
    }


def init_tracing(path: pathlib.Path = DEFAULT_TRACE_PATH) -> Tracer:
    """Idempotent per path: repeated calls with the same path share one provider."""
    path = pathlib.Path(path)
    with _lock:
        provider = _providers.get(path)
        if provider is None:
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(JsonlExporter(path)))
            _providers[path] = provider
    return provider.get_tracer("optiflow")


def get_tracer() -> Tracer:
    return init_tracing()


def run_tracer(run_id: str) -> Tracer:
    return init_tracing(TRACE_DIR / f"{run_id}.jsonl")


def trace_path(run_id: str) -> pathlib.Path:
    return TRACE_DIR / f"{run_id}.jsonl"
