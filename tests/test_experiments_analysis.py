"""One-off runs must never be presented as a comparison."""

import pandas as pd

from optiflow.experiments.analyze_results import analysis


def _row(experiment, program, variant, speedup, critic="crewai"):
    return {"run_id": f"{experiment}-{program}-{variant}-{critic}", "experiment": experiment,
            "program_id": program, "category": "sorting", "architecture": "sequential",
            "messaging": "blackboard", "prompt_style": "structured", "persona": "default",
            "critic_backend": critic, "model_config": "single-cloud", "variant": variant,
            "success": 1, "speedup": speedup, "cost_usd": 0.0, "latency_s": 10.0, "total_tokens": 0,
            "attempts": 1, "messages": 0, "deliveries": 0, "message_bytes": 0, "cpu_speedup": speedup,
            "guardrail_flags": 0, "a2a_calls": 0, "a2a_latency_ms": 0, "repeat": 0, "started_at": 1.0,
            "winning_strategy": ""}


def test_adhoc_runs_get_no_factor_comparisons_but_designed_experiments_do():
    rows = []
    for i, p in enumerate(f"prog{n}" for n in range(6)):
        rows.append(_row("e6_interop", p, "full", 2.0 + i, "crewai"))
        rows.append(_row("e6_interop", p, "full", 3.0 + i, "adk_a2a"))
    # a hand-picked dashboard run next to unrelated baselines
    rows.append(_row("dashboard", "bubble_sort", "full", 234.0, "adk_a2a"))
    rows.append(_row("dashboard", "lcs", "rule_only", 1.0, "crewai"))

    result = analysis(pd.DataFrame(rows))
    adhoc = result["experiments"]["dashboard"]
    assert adhoc["varied"] == [] and adhoc["tests"] == {}
    assert list(adhoc["summaries"]) == ["all"]          # a single summary row, nothing to compare

    designed = result["experiments"]["e6_interop"]
    assert designed["varied"] == ["critic_backend"]
    assert {r["critic_backend"] for r in designed["summaries"]["critic_backend"]} == {"crewai", "adk_a2a"}
    assert designed["tests"]["critic_backend"]["paired_programs"] == 6
