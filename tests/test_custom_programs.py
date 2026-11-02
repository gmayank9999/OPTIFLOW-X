"""User-submitted programs (workspace "Paste my code"): validation, API
wiring, isolation from the versioned results, and the Docker-backed
reference-output generation."""

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from optiflow.api import main as api_main
from optiflow.tools import custom, registry

client = TestClient(api_main.app)

SUM_PROGRAM = r"""
#include <stdio.h>
int main(void) {
    int n; long long s = 0;
    if (scanf("%d", &n) != 1) return 1;
    for (int i = 0; i < n; i++) { int x; scanf("%d", &x); s += x; }
    printf("%lld\n", s);
    return 0;
}
"""


def docker_ready() -> bool:
    try:
        from optiflow.tools.sandbox import _get_client

        return bool(_get_client().images.list(name="optiflow-sandbox"))
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def custom_root(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CUSTOM_ROOT", tmp_path / "custom")
    return tmp_path / "custom"


# ------------------------------------------------------------- validation

@pytest.mark.parametrize("source, language, message", [
    ("   \n", "c", "empty"),
    ("int x = 1;", "c", "main()"),
])
def test_validate_submission_rejects_bad_source(source, language, message):
    with pytest.raises(custom.CustomProgramError, match=message):
        custom.validate_submission(source, language, [])


def test_validate_submission_rejects_oversized_source():
    with pytest.raises(custom.CustomProgramError, match="larger than"):
        custom.validate_submission("int main(){}" + " " * custom.MAX_SOURCE_BYTES, "c", [])


def test_validate_submission_rejects_oversized_input():
    with pytest.raises(custom.CustomProgramError, match="Test input 1"):
        custom.validate_submission(SUM_PROGRAM, "c", ["x" * (custom.MAX_INPUT_BYTES + 1)])


def test_validate_submission_accepts_a_program():
    custom.validate_submission(SUM_PROGRAM, "c", ["3\n1 2 3\n"])


# ------------------------------------------------------------------- API

def test_api_rejects_empty_source_with_a_readable_message():
    response = client.post("/api/runs", json={"source": "   "})
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_api_rejects_source_without_main():
    assert client.post("/api/runs", json={"source": "int x;"}).status_code == 422


def test_api_rejects_bad_language():
    assert client.post("/api/runs", json={"source": SUM_PROGRAM, "language": "rust"}).status_code == 422


def test_api_queues_custom_source_under_a_custom_id(monkeypatch):
    queued = []
    monkeypatch.setattr(api_main, "_ensure_worker", lambda: None)
    monkeypatch.setattr(api_main._queue, "put", queued.append)
    response = client.post("/api/runs", json={"source": SUM_PROGRAM, "variant": "flags_only",
                                              "test_inputs": ["3\n1 2 3\n", "  "]})
    assert response.status_code == 200
    body = response.json()
    assert body["program_id"].startswith("custom_")
    run_id, _cfg, program_id, spec = queued[0]
    assert program_id == body["program_id"] and run_id == body["run_id"]
    assert spec["test_inputs"] == ["3\n1 2 3\n"]  # blank inputs are dropped
    # The original source is available to the results view while queued.
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["original_source"] == SUM_PROGRAM
    assert "source" not in detail["config"]


def test_api_still_requires_a_program_when_no_source():
    assert client.post("/api/runs", json={}).status_code == 404


# ---------------------------------------------------- isolation / registry

def test_custom_ids_resolve_under_the_custom_root_only(custom_root):
    (custom_root / "custom_abc").mkdir(parents=True)
    assert registry._program_dir("custom_abc") == custom_root / "custom_abc"
    with pytest.raises(KeyError):
        registry._program_dir("custom_missing")
    assert "custom_abc" not in registry.list_programs()


def test_custom_runs_stay_out_of_runs_csv(tmp_path, monkeypatch):
    from optiflow.core.schemas import RunState
    from optiflow.experiments import store

    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(store, "RUNS_CSV", tmp_path / "runs.csv")
    state = RunState(run_id="r1", program_id="custom_abc123", architecture="sequential", messaging="blackboard")
    store.save_run(state, type("Cfg", (), {"experiment": "dashboard"})(), [])
    assert (tmp_path / "runs" / "r1" / "report.json").exists()
    assert not (tmp_path / "runs.csv").exists()


# --------------------------------------------------- Docker-backed reference

@pytest.mark.skipif(not docker_ready(), reason="needs Docker and the optiflow-sandbox image")
def test_materialize_generates_expected_output_from_the_original(custom_root):
    pid = custom.new_program_id()
    meta = custom.materialize(pid, SUM_PROGRAM, "c", ["3\n1 2 3\n", "5\n10 20 30 40 50\n"])
    root = custom_root / pid
    assert (root / "expected" / "out1.txt").read_text().strip() == "6"
    assert (root / "expected" / "out2.txt").read_text().strip() == "150"
    assert meta["bench_input"] == "inputs/in2.txt"  # the larger input is timed
    assert json.loads((root / "meta.json").read_text())["category"] == "custom"


@pytest.mark.skipif(not docker_ready(), reason="needs Docker and the optiflow-sandbox image")
@pytest.mark.parametrize("source, message", [
    ("int main(void) { return 1 +; }", "does not compile"),
    ("int main(void) { return 3; }", "exited with status 3"),
    ('#include <stdio.h>\n#include <stdlib.h>\nint main(void){printf("%p\\n", malloc(8));return 0;}',
     "different output"),
])
def test_materialize_explains_unusable_originals_and_cleans_up(custom_root, source, message):
    pid = custom.new_program_id()
    with pytest.raises(custom.CustomProgramError, match=message):
        custom.materialize(pid, source, "c", [])
    assert not (custom_root / pid).exists()


# ------------------------------------- non-deterministic originals (explained)

# Ignores scanf's result. With no example input `n` is leftover stack memory,
# and the stack address printed with it changes on every run (ASLR).
UNCHECKED_SCANF = r"""
#include <stdio.h>
int main(void) { int n; scanf("%d", &n); printf("%d %p\n", n, (void *)&n); return 0; }
"""


def test_explanation_names_the_unchecked_read_and_the_first_differing_line():
    message = custom.explain_nondeterminism(UNCHECKED_SCANF, "c", "your program", "",
                                            "5 0x7ffc1\n", "5 0x7ffc9\n")
    assert "no example input" in message
    assert "memory address" in message
    assert "output line 1" in message and "run 1: 5 0x7ffc1" in message and "run 2: 5 0x7ffc9" in message
    assert "scanf(" in message  # concrete fix, not just a diagnosis


def test_explanation_blames_randomness_and_ignores_comments():
    seeded = "int main(void){ srand(time(0)); return rand() % 2; }"
    assert "It uses random numbers" in custom.explain_nondeterminism(seeded, "c", "x", "1\n", "1\n", "0\n")
    commented = "// uses rand() someday\nint main(void){ return 0; }"
    message = custom.explain_nondeterminism(commented, "c", "x", "1\n", "1\n", "0\n")
    assert "It uses random numbers" not in message and "uninitialised memory" in message


def test_explanation_does_not_accuse_input_when_input_was_given():
    message = custom.explain_nondeterminism(UNCHECKED_SCANF, "c", "x", "5\n", "a\n", "b\n")
    assert "no example input" not in message


def test_explanation_picks_the_compiler_for_the_language():
    assert "g++ -O2" in custom.explain_nondeterminism("int main(){}", "cpp", "x", "", "a", "b")


@pytest.mark.skipif(not docker_ready(), reason="needs Docker and the optiflow-sandbox image")
def test_unstable_original_is_rejected_with_the_cause_and_never_accepted(custom_root):
    pid = custom.new_program_id()
    with pytest.raises(custom.CustomProgramError) as exc:
        custom.materialize(pid, UNCHECKED_SCANF, "c", [])
    message = str(exc.value)
    assert "different output on two identical runs" in message
    assert "no example input" in message and "How to fix it" in message
    assert not (custom_root / pid).exists()  # no reference was written for an unstable program


@pytest.mark.skipif(not docker_ready(), reason="needs Docker and the optiflow-sandbox image")
def test_same_read_pattern_is_accepted_once_the_input_is_given(custom_root):
    source = r'''#include <stdio.h>
int main(void) { int n; scanf("%d", &n); printf("%d\n", n * 2); return 0; }
'''
    pid = custom.new_program_id()
    custom.materialize(pid, source, "c", ["21\n"])
    assert (custom_root / pid / "expected" / "out1.txt").read_text().strip() == "42"


# ------------------------------------- a visitor's code never reaches public pages

def _write_report(runs_dir, run_id, program_id, mtime):
    import os

    d = runs_dir / run_id
    d.mkdir(parents=True)
    row = {"run_id": run_id, "program_id": program_id, "speedup": "9.0", "architecture": "sequential",
           "messaging": "blackboard"}
    state = {"program_id": program_id, "best": {"speedup": 9.0}, "history": [], "usage": {},
             "guardrail_events": [{"agent": "analyzer", "attempt": None, "stage": "x", "detail": "secret source"}]}
    (d / "report.json").write_text(json.dumps({"config": {}, "state": state, "row": row}))
    (d / "diff.patch").write_text("+ visitor code")
    os.utime(d, (mtime, mtime))


def test_public_pages_skip_custom_runs(tmp_path, monkeypatch):
    from optiflow.api import requirements as requirements_api

    runs = tmp_path / "runs"
    _write_report(runs, "benchmarkrun", "matmul_naive", 1_000)
    _write_report(runs, "visitorrun", "custom_abc123", 2_000)  # newer: would win a "latest" pick
    from optiflow.experiments import store

    for module in (store, requirements_api, api_main):
        monkeypatch.setattr(module, "RUNS_DIR", runs)

    sample = requirements_api.get_requirements_data()["req3_pydantic"]["sample_report"]
    assert sample["program_id"] == "matmul_naive"

    events = client.get("/api/guardrails/events").json()
    assert all(not e["program_id"].startswith("custom_") for e in events)
