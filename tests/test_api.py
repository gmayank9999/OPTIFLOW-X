import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from optiflow.api.main import app

client = TestClient(app)


def test_programs_endpoint_lists_benchmark_suite():
    response = client.get("/programs")
    assert response.status_code == 200
    programs = response.json()
    ids = {p["id"] for p in programs}
    assert "matmul_naive" in ids
    assert len(programs) == 10


def test_start_run_rejects_unknown_program():
    response = client.post("/runs", json={"program_id": "does_not_exist"})
    assert response.status_code == 404


def test_get_run_404_for_unknown_run_id():
    response = client.get("/runs/nonexistent")
    assert response.status_code == 404
