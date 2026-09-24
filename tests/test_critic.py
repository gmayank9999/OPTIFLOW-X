from optiflow.agents.critic import decide
from optiflow.core.budget import RunBudget
from optiflow.core.schemas import BuildResult, CompareResult, TestResult


def make_budget():
    return RunBudget(max_attempts=5, max_usd=1.0)


def test_rejects_on_compile_failure():
    build = BuildResult(ok=False, stderr="syntax error")
    verdict = decide(build, None, None, make_budget())
    assert not verdict.accepted
    assert verdict.reason == "compile_error"


def test_rejects_on_wrong_output():
    build = BuildResult(ok=True, candidate_id="x")
    tests = TestResult(all_pass=False, failed_cases=["in2.txt"])
    verdict = decide(build, tests, None, make_budget())
    assert not verdict.accepted
    assert verdict.reason == "wrong_output"


def test_rejects_below_speedup_threshold():
    build = BuildResult(ok=True, candidate_id="x")
    tests = TestResult(all_pass=True)
    compare = CompareResult(speedup=1.02, p_value=0.01, accepted_by_rule=False)
    verdict = decide(build, tests, compare, make_budget())
    assert not verdict.accepted
    assert verdict.reason == "no_significant_gain"


def test_rejects_on_insignificant_p_value_despite_good_speedup():
    build = BuildResult(ok=True, candidate_id="x")
    tests = TestResult(all_pass=True)
    compare = CompareResult(speedup=1.5, p_value=0.2, accepted_by_rule=False)
    verdict = decide(build, tests, compare, make_budget())
    assert not verdict.accepted
    assert verdict.reason == "no_significant_gain"


def test_accepts_valid_speedup():
    build = BuildResult(ok=True, candidate_id="x")
    tests = TestResult(all_pass=True)
    compare = CompareResult(speedup=3.9, p_value=0.001, accepted_by_rule=True)
    verdict = decide(build, tests, compare, make_budget())
    assert verdict.accepted
    assert verdict.speedup == 3.9


def test_stops_when_attempt_budget_exhausted():
    budget = RunBudget(max_attempts=2, max_usd=1.0)
    build = BuildResult(ok=False, stderr="err")
    decide(build, None, None, budget)
    verdict = decide(build, None, None, budget)
    assert verdict.stop is True


def test_stops_when_two_consecutive_attempts_barely_improve_over_best():
    budget = RunBudget(max_attempts=10, max_usd=1.0)
    build = BuildResult(ok=True, candidate_id="x")
    tests = TestResult(all_pass=True)
    # Established best is 2.0x; each new attempt gains under 3% over it.
    barely1 = CompareResult(speedup=2.03, p_value=0.001, accepted_by_rule=True)
    decide(build, tests, barely1, budget, current_best_speedup=2.0)
    barely2 = CompareResult(speedup=2.05, p_value=0.001, accepted_by_rule=True)
    verdict = decide(build, tests, barely2, budget, current_best_speedup=2.0)
    assert verdict.stop is True


def test_does_not_stop_when_improvement_is_substantial():
    budget = RunBudget(max_attempts=10, max_usd=1.0)
    build = BuildResult(ok=True, candidate_id="x")
    tests = TestResult(all_pass=True)
    big_gain = CompareResult(speedup=3.9, p_value=0.001, accepted_by_rule=True)
    verdict = decide(build, tests, big_gain, budget, current_best_speedup=1.0)
    assert verdict.stop is False
