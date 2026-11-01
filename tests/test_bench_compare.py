"""Benchmark statistics and the hrtime harness."""

import json

from optiflow.core.schemas import BenchResult
from optiflow.tools import bench


def _result(median_ms: float, runtimes: list[float], failed: int = 0) -> BenchResult:
    return BenchResult(
        runtimes_ms=runtimes, median_ms=median_ms, mean_ms=median_ms, std_ms=0.0, p95_ms=median_ms,
        cv=0.0, peak_mem_kb=1000, cpu_median_ms=median_ms, failed_runs=failed,
    )


def test_clear_speedup_is_accepted_with_small_p():
    base = _result(100.0, [100.0 + i for i in range(10)])
    cand = _result(50.0, [50.0 + i for i in range(10)])
    r = bench.compare_results(base, cand)
    assert abs(r.speedup - 100.0 / 50.0) < 1e-9 and r.p_value < 0.001 and r.accepted_by_rule


def test_identical_distributions_are_not_accepted():
    samples = [100.0 + (i % 3) for i in range(10)]
    r = bench.compare_results(_result(101.0, samples), _result(101.0, list(samples)))
    assert not r.accepted_by_rule and r.p_value > 0.05


def test_failed_candidate_runs_mean_no_measurement():
    r = bench.compare_results(_result(100.0, [100.0] * 10), _result(10.0, [10.0] * 9, failed=1))
    assert r.speedup == 0.0 and not r.accepted_by_rule


def test_summarize_drops_failed_runs_and_reports_them():
    samples = [(100.0, 99.0, 2000, 0), (101.0, 100.0, 2100, 0), (5.0, 5.0, 100, 139)]
    r = bench.summarize(samples)
    assert r.runtimes_ms == [100.0, 101.0] and r.failed_runs == 1 and r.peak_mem_kb == 2100


def test_adaptive_runs_scale_with_runtime(tmp_path, monkeypatch):
    path = tmp_path / "stability.json"
    path.write_text(json.dumps({"programs": {"fast": {"median_ms": 20.0}, "slow": {"median_ms": 2000.0}}}))
    monkeypatch.setattr(bench, "STABILITY_PATH", path)
    assert bench.adaptive_runs("fast") == bench.MAX_ADAPTIVE_RUNS
    assert bench.adaptive_runs("slow") == bench.DEFAULT_RUNS
    assert bench.adaptive_runs("unknown") == bench.DEFAULT_RUNS


def test_identical_binary_against_itself_is_within_noise():
    """Section 7.3: the same program benchmarked against itself, interleaved."""
    cid = bench.baseline_candidate("fib_recursive")
    r = bench.compare(cid, "fib_recursive", n=5)
    assert 0.9 < r.speedup < 1.1
    assert not r.accepted_by_rule
    assert len(r.baseline.runtimes_ms) == 5 and len(r.candidate.runtimes_ms) == 5


# --- the current best is timed in the same session and tested too -------------

def _timed(runtimes):
    """A real BenchResult from raw wall-time samples (ms)."""
    return bench.summarize([(t, t, 1000, 0) for t in runtimes])


def test_reference_indistinguishable_from_candidate_is_not_better():
    """The 189x -> 234x problem: both beat the baseline hugely, but ~5 ms
    candidates are noise-limited, so one is not demonstrably faster."""
    base = _timed([1100.0 + 3 * i for i in range(10)])
    cand = _timed([4.0, 6.0, 5.0, 7.0, 4.5, 5.5, 6.5, 4.2, 6.2, 5.2])
    ref = _timed([4.1, 6.1, 5.1, 7.1, 4.6, 5.6, 6.6, 4.3, 6.3, 5.3])
    r = bench.compare_results(base, cand, ref)
    assert r.accepted_by_rule                       # clear win over the baseline
    assert r.vs_best_p_value > 0.05                 # but no evidence it beats the best
    assert 0.9 < r.vs_best_speedup < 1.1
    assert r.low_precision                          # median ~5 ms, CV ~19%: flagged


def test_clearly_faster_than_the_reference_is_detected():
    base = _timed([1000.0 + i for i in range(10)])
    ref = _timed([200.0 + 0.1 * i for i in range(10)])
    cand = _timed([100.0 + 0.1 * i for i in range(10)])
    r = bench.compare_results(base, cand, ref)
    assert r.vs_best_speedup > 1.9 and r.vs_best_p_value < 0.01
    assert not r.low_precision                      # 100 ms, CV < 1%


def test_no_reference_means_no_vs_best_fields():
    r = bench.compare_results(_timed([100.0 + i for i in range(10)]), _timed([50.0 + i for i in range(10)]))
    assert r.vs_best_speedup is None and r.vs_best_p_value is None and r.reference is None
