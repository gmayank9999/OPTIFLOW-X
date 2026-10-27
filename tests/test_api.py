import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from optiflow.api.main import app

client = TestClient(app)


def test_programs_endpoint_lists_benchmark_suite():
    response = client.get("/api/programs")
    assert response.status_code == 200
    programs = response.json()
    assert "matmul_naive" in {p["id"] for p in programs}
    assert len(programs) == 50


def test_program_detail_has_source_loops_and_features():
    body = client.get("/api/programs/matmul_naive").json()
    assert "int main" in body["source"]
    assert body["features"]["stride_mismatch"] == 1.0
    assert len(body["inputs"]) == 3


def test_unknown_program_404():
    assert client.get("/api/programs/nope").status_code == 404


def test_start_run_rejects_unknown_program():
    assert client.post("/api/runs", json={"program_id": "does_not_exist"}).status_code == 404


def test_start_run_validates_config():
    response = client.post("/api/runs", json={"program_id": "matmul_naive", "architecture": "anarchy"})
    assert response.status_code == 422


def test_get_run_404_for_unknown_run_id():
    assert client.get("/api/runs/nonexistent").status_code == 404


def test_health_reports_sandbox_and_keys_without_values():
    body = client.get("/api/health").json()
    assert set(body["keys"]) == {"GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY"}
    assert all(isinstance(v, bool) for v in body["keys"].values())


@pytest.mark.parametrize("path", ["/api/runs", "/api/metrics/agents", "/api/experiments/summary", "/api/ml", "/api/stability"])
def test_read_endpoints_respond(path):
    assert client.get(path).status_code == 200


def test_write_endpoint_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("OPTIFLOW_API_TOKEN", "s3cret")
    body = {"program_id": "does_not_exist"}
    assert client.post("/api/runs", json=body).status_code == 401
    assert client.post("/api/runs", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    # right token gets past auth (then 404 for the unknown program)
    assert client.post("/api/runs", json=body, headers={"Authorization": "Bearer s3cret"}).status_code == 404
    assert client.post("/api/runs", json=body, headers={"X-API-Token": "s3cret"}).status_code == 404
    assert client.get("/api/health").json()["write_requires_token"] is True
