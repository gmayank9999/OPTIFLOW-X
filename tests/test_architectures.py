"""End-to-end runs of all three architectures with a scripted LLM.

Everything is real -- tree-sitter, perf/profiling, the Docker sandbox,
compilation, the reference tests, the sanitizer pass, interleaved
benchmarking, the Critic's rules, tracing and run persistence -- except
the language model, which is replaced by a stub that answers each prompt
type with a fixed, valid response. This is what proves the orchestration
works (including peer-to-peer and broadcast messaging) without an API key.

palindrome_count is used because its sweep template (expand-around-center,
O(n^2) instead of O(n^3)) is a guaranteed, large speedup. (An earlier
version used substring_naive + REWRITE, and the Critic correctly rejected REWRITE
at ~0.9x: on random text the naive scan already mismatches on the first
character almost every time.)
"""

import json

import pytest

from optiflow.agents.mcp_tools import DirectToolClient
from optiflow.architectures.base import RunConfig, build
from optiflow.core.schemas import TokenUsage
from optiflow.experiments import store
from optiflow.ml.templates import TEMPLATES

PROGRAM = "palindrome_count"
REWRITE = TEMPLATES[PROGRAM]["algorithmic"]


def fake_call(agent, description, expected_output, **kwargs):
    usage = TokenUsage(prompt_tokens=len(description) // 4, completion_tokens=50, calls=1, cost_usd=0.0001)
    if "OptimizationPlan" in expected_output:
        plan = {"strategies": [{"name": "algorithm_change", "target": "main", "params": {},
                                "rationale": "naive O(n*m) scan", "confidence": 0.8}],
                "compiler": "gcc", "flags": ["-O2"]}
        return f"```json\n{json.dumps(plan)}\n```", usage
    if "APPLY THESE TRANSFORMATIONS" in description:
        return f"```c\n{REWRITE}```", usage
    if '"action"' in expected_output:
        return '{"action": "plan", "reason": "keep going"}', usage
    return "stub text", usage


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr("optiflow.core.llm.call", fake_call)
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(store, "RUNS_CSV", tmp_path / "runs.csv")
    monkeypatch.setattr(store, "EXPERIENCE", tmp_path / "experience.jsonl")
    monkeypatch.setattr("optiflow.observability.tracing.TRACE_DIR", tmp_path / "traces")


@pytest.mark.parametrize("architecture,messaging", [
    ("sequential", "blackboard"),
    ("hierarchical", "p2p"),
    ("event", "broadcast"),
])
def test_architecture_accepts_a_verified_rewrite(architecture, messaging, tmp_path):
    cfg = RunConfig(architecture=architecture, messaging=messaging, max_attempts=2, bench_n=5, max_usd_per_run=1.0)
    events = []
    state = build(cfg, emit=events.append, tools=DirectToolClient()).run(PROGRAM)

    assert state.history, (state.stop_reason, state.error[-1500:])
    first = state.history[0]
    assert first["plan"]["strategies"][0]["name"] == "algorithmic"  # alias normalized
    assert first["tests"]["all_pass"] and first["tests"]["sanitizer_ok"] is True
    assert first["verdict"]["accepted"], first["verdict"]
    assert state.best["speedup"] > 1.05
    assert state.best["candidate"]["source"].strip() == REWRITE.strip()

    # The stub proposes the same rewrite again; on top of the best that's
    # an identical program, which must be rejected without benchmarking.
    if len(state.history) > 1:
        assert state.history[1]["verdict"]["reason"] == "no_change"

    # Accounting, persistence and the event stream.
    assert state.usage.calls > 0 and state.usage.cost_usd > 0
    assert "strategist" in state.usage_by_agent
    assert state.messaging_stats["mechanism"] == messaging and state.messaging_stats["messages"] > 0
    rows = store.read_rows(store.RUNS_CSV)
    assert rows[-1]["run_id"] == state.run_id and rows[-1]["success"] == "1"
    assert (store.RUNS_DIR / state.run_id / "best.c").read_text().strip() == REWRITE.strip()
    types = [e["type"] for e in events]
    assert types[0] == "run_start" and types[-1] == "run_end" and "attempt_end" in types


def test_messaging_changes_what_the_strategist_sees():
    """Broadcast delivers more to every agent than peer-to-peer does."""
    stats = {}
    for messaging in ("p2p", "broadcast"):
        cfg = RunConfig(architecture="sequential", messaging=messaging, max_attempts=1, bench_n=3)
        state = build(cfg, tools=DirectToolClient()).run(PROGRAM)
        stats[messaging] = state.messaging_stats
    assert stats["broadcast"]["deliveries"] > stats["p2p"]["deliveries"]


def test_flags_only_baseline_needs_no_llm(monkeypatch):
    def no_llm(*a, **k):
        raise AssertionError("flags_only must not call an LLM")
    monkeypatch.setattr("optiflow.core.llm.call", no_llm)
    cfg = RunConfig(variant="flags_only", max_attempts=3, bench_n=3)
    state = build(cfg, tools=DirectToolClient()).run(PROGRAM)
    assert len(state.history) == 1
    assert state.history[0]["plan"]["flags"] == ["-O3", "-march=native"]
    assert state.stop_reason == "no_more_strategies"
    assert state.usage.calls == 0


def test_unparseable_plan_becomes_a_rejected_attempt(monkeypatch):
    def bad_plan(agent, description, expected_output, **kwargs):
        if "OptimizationPlan" in expected_output:
            return "I think you should make it faster.", TokenUsage(calls=1)
        return fake_call(agent, description, expected_output)
    monkeypatch.setattr("optiflow.core.llm.call", bad_plan)
    cfg = RunConfig(max_attempts=1, bench_n=3)
    state = build(cfg, tools=DirectToolClient()).run(PROGRAM)
    assert state.history[0]["verdict"]["reason"] == "plan_error"
    assert not state.error
