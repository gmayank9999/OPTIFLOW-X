"""Regression test: a candidate too fast for /usr/bin/time's 10ms
resolution to register (median_ms == 0) must not be scored as a 0x
speedup -- that would make the Critic reject the best possible outcome."""

from unittest.mock import patch

from optiflow.core.schemas import BenchResult
from optiflow.tools import bench


def _result(median_ms: float, runtimes: list[float]) -> BenchResult:
    return BenchResult(
        runtimes_ms=runtimes, median_ms=median_ms, mean_ms=median_ms,
        std_ms=0.0, p95_ms=median_ms, cv=0.0, peak_mem_kb=1000,
    )


def test_zero_median_candidate_is_not_scored_as_zero_speedup():
    baseline = _result(1000.0, [1000.0] * 10)
    candidate = _result(0.0, [0.0] * 10)

    with patch.object(bench, "get_baseline", return_value=baseline), \
         patch.object(bench, "run", return_value=candidate):
        result = bench.compare("fake_candidate", "fake_program", n=10)

    assert result.speedup > 1.0
    assert result.speedup == 1000.0  # baseline / 1ms floor


def test_normal_speedup_is_unaffected_by_the_floor():
    baseline = _result(1000.0, [1000.0] * 10)
    candidate = _result(500.0, [500.0] * 10)

    with patch.object(bench, "get_baseline", return_value=baseline), \
         patch.object(bench, "run", return_value=candidate):
        result = bench.compare("fake_candidate", "fake_program", n=10)

    assert result.speedup == 2.0
