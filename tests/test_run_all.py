import pytest

from optiflow.experiments import run_all as ra


class FakeRunner:
    """Records commands; returns scripted exit codes for run_matrix calls."""

    def __init__(self, codes=None):
        self.cmds, self.codes = [], list(codes or [])

    def __call__(self, cmd):
        self.cmds.append(cmd)
        if "run_matrix" in " ".join(cmd) and self.codes:
            return self.codes.pop(0)
        return 0

    def experiments(self):
        paths = [next(a for a in c if a.endswith(".yaml")) for c in self.cmds if "run_matrix" in " ".join(c)]
        return [p.replace("\\", "/").split("/")[-1].removesuffix(".yaml") for p in paths]


def test_runs_every_experiment_in_priority_order_with_two_passes_and_analysis():
    r = FakeRunner()
    assert ra.run_all(runner=r) == 0
    assert r.experiments() == [n for n in ra.ORDER for _ in range(2)]
    analyses = [c for c in r.cmds if "analyze_results" in " ".join(c)]
    assert len(analyses) == len(ra.ORDER)          # refreshed after each experiment


def test_a_quota_stop_ends_the_whole_run_immediately():
    r = FakeRunner(codes=[0, 0, ra.QUOTA_EXIT])    # e6 pass 1, e6 pass 2, e3 pass 1 hits the quota
    assert ra.run_all(runner=r) == ra.QUOTA_EXIT
    assert r.experiments() == ["e6_interop", "e6_interop", "e3_prompting"]   # nothing after it


def test_only_restricts_the_experiments_and_keeps_priority_order():
    r = FakeRunner()
    ra.run_all(only=["e7_repeats", "e6_interop"], runner=r)
    assert r.experiments() == ["e6_interop", "e6_interop", "e7_repeats", "e7_repeats"]


def test_dry_run_runs_each_config_once_and_never_analyzes():
    r = FakeRunner()
    ra.run_all(dry_run=True, runner=r)
    assert r.experiments() == list(ra.ORDER)
    assert all("--dry-run" in c for c in r.cmds) and not any("analyze_results" in " ".join(c) for c in r.cmds)


def test_unknown_experiment_is_rejected():
    with pytest.raises(SystemExit):
        ra.run_all(only=["e99_nope"], runner=FakeRunner())


def test_second_run_is_refused_while_the_lock_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "LOCK", tmp_path / "run_all.lock")
    ra._acquire_lock()
    assert ra.LOCK.exists()
    with pytest.raises(SystemExit) as exc:
        ra._acquire_lock()
    assert "another experiment run" in str(exc.value)
    ra.LOCK.unlink()


def test_every_listed_experiment_has_a_config_file():
    for name in ra.ORDER:
        assert (ra.CONFIG_DIR / f"{name}.yaml").exists()
