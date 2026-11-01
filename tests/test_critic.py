from optiflow.agents.critic import decide
from optiflow.core.budget import RunBudget
from optiflow.core.schemas import BuildResult, CompareResult, TestResult


def make_budget(**kw):
    return RunBudget(max_attempts=kw.get("max_attempts", 5), max_usd=kw.get("max_usd", 1.0))


OK_BUILD = BuildResult(ok=True, candidate_id="x")
OK_TESTS = TestResult(all_pass=True, sanitizer_ok=True)


def cmp(speedup, p=0.001):
    return CompareResult(speedup=speedup, p_value=p, accepted_by_rule=speedup >= 1.05 and p < 0.05)


def test_rejects_on_compile_failure():
    verdict = decide(BuildResult(ok=False, stderr="syntax error"), None, None, make_budget())
    assert not verdict.accepted and verdict.reason == "compile_error"


def test_rejects_on_wrong_output_with_case_details():
    tests = TestResult(all_pass=False, failed_cases=["inputs/in2.txt"],
                       details={"inputs/in2.txt": {"status": "wrong_output", "actual_head": "41", "expected_head": "42"}})
    verdict = decide(OK_BUILD, tests, None, make_budget())
    assert verdict.reason == "wrong_output"
    assert "in2" in verdict.feedback_for_strategist and "42" in verdict.feedback_for_strategist


def test_rejects_on_sanitizer_failure():
    tests = TestResult(all_pass=False, failed_cases=["sanitizer"], sanitizer_ok=False,
                       sanitizer_report="heap-buffer-overflow")
    verdict = decide(OK_BUILD, tests, None, make_budget())
    assert verdict.reason == "sanitizer_error" and "heap-buffer-overflow" in verdict.feedback_for_strategist


def test_rejects_below_speedup_threshold():
    assert decide(OK_BUILD, OK_TESTS, cmp(1.02), make_budget()).reason == "no_significant_gain"


def test_rejects_on_insignificant_p_value_despite_good_speedup():
    assert decide(OK_BUILD, OK_TESTS, cmp(1.5, p=0.2), make_budget()).reason == "no_significant_gain"


def test_rejects_when_not_better_than_current_best():
    verdict = decide(OK_BUILD, OK_TESTS, cmp(3.0), make_budget(), current_best_speedup=3.5)
    assert not verdict.accepted and verdict.reason == "no_improvement"


def test_accepts_valid_speedup():
    verdict = decide(OK_BUILD, OK_TESTS, cmp(3.9), make_budget())
    assert verdict.accepted and verdict.speedup == 3.9


def test_pre_rejected_reason_passes_through():
    verdict = decide(BuildResult(ok=False), None, None, make_budget(), rejected_reason="plan_error", rejected_detail="no JSON")
    assert verdict.reason == "plan_error"


def test_stops_when_attempt_budget_exhausted():
    budget = make_budget(max_attempts=2)
    decide(OK_BUILD, OK_TESTS, cmp(2.0), budget)
    verdict = decide(OK_BUILD, OK_TESTS, cmp(3.0), budget, current_best_speedup=2.0)
    assert verdict.stop and verdict.stop_reason == "attempt_budget"


def test_stops_when_two_consecutive_accepts_barely_improve():
    budget = make_budget(max_attempts=10)
    # +2.5% then +2.4%: each clears the 2% noise margin but not the 3% bar.
    decide(OK_BUILD, OK_TESTS, cmp(2.05), budget, current_best_speedup=2.0)
    verdict = decide(OK_BUILD, OK_TESTS, cmp(2.10), budget, current_best_speedup=2.05)
    assert verdict.stop and verdict.stop_reason == "diminishing_returns"


def test_two_rejections_do_not_stop_the_run():
    # The old rule counted rejections as "no gain" and ended runs after two misses.
    budget = make_budget(max_attempts=10)
    decide(BuildResult(ok=False, stderr="e"), None, None, budget)
    verdict = decide(BuildResult(ok=False, stderr="e"), None, None, budget)
    assert not verdict.stop


def test_three_rejections_in_a_row_stop_the_run():
    budget = make_budget(max_attempts=10)
    for _ in range(2):
        decide(BuildResult(ok=False, stderr="e"), None, None, budget)
    verdict = decide(BuildResult(ok=False, stderr="e"), None, None, budget)
    assert verdict.stop and verdict.stop_reason == "consecutive_rejects"


def test_cost_cap_stops_the_run():
    budget = make_budget(max_usd=0.01)
    budget.record_call(0.02)
    verdict = decide(OK_BUILD, OK_TESTS, cmp(2.0), budget)
    assert verdict.stop and verdict.stop_reason == "cost_cap"


def test_does_not_stop_when_improvement_is_substantial():
    verdict = decide(OK_BUILD, OK_TESTS, cmp(3.9), make_budget(max_attempts=10))
    assert verdict.stop is False


# --- "better than the best so far" is a statistical claim too -----------------

def cmp_vs_best(speedup, vs_best, vs_p, p=0.001):
    return CompareResult(speedup=speedup, p_value=p, accepted_by_rule=True,
                         vs_best_speedup=vs_best, vs_best_p_value=vs_p)


def test_beating_the_baseline_but_not_the_best_in_the_same_session_is_rejected():
    verdict = decide(OK_BUILD, OK_TESTS, cmp_vs_best(234.0, vs_best=1.02, vs_p=0.31), make_budget(),
                     current_best_speedup=189.0)
    assert not verdict.accepted and verdict.reason == "no_improvement"
    assert "same session" in verdict.feedback_for_strategist and "0.310" in verdict.feedback_for_strategist


def test_a_significant_gain_over_the_best_is_accepted_and_drives_the_stop_rule():
    verdict = decide(OK_BUILD, OK_TESTS, cmp_vs_best(300.0, vs_best=1.5, vs_p=0.001), make_budget(),
                     current_best_speedup=200.0)
    assert verdict.accepted and verdict.speedup == 300.0
    assert "+50.0%" in verdict.feedback_for_strategist      # measured vs best, not 300/200


def test_significant_but_tiny_gain_over_the_best_is_not_enough():
    verdict = decide(OK_BUILD, OK_TESTS, cmp_vs_best(210.0, vs_best=1.005, vs_p=0.001), make_budget(),
                     current_best_speedup=200.0)
    assert verdict.reason == "no_improvement"


def test_first_accepted_candidate_needs_no_best_comparison():
    verdict = decide(OK_BUILD, OK_TESTS, cmp_vs_best(5.0, vs_best=5.0, vs_p=0.0001), make_budget(),
                     current_best_speedup=1.0)
    assert verdict.accepted
