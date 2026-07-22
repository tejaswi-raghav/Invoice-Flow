"""API tests via FastAPI's TestClient."""
import os

from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)
HERE = os.path.dirname(__file__)


def _load(name):
    with open(os.path.join(HERE, "..", "app", "samples", name), "r", encoding="utf-8") as fh:
        return fh.read()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_validate_good():
    r = client.post("/validate", json={"xml": _load("good.xml")})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    assert body["verdict"]["fatal"] == 0


def test_test_endpoint_all_pass():
    r = client.post("/test", json={"xml": _load("good.xml")})
    assert r.status_code == 200
    body = r.json()
    assert body["all_passed"] is True
    assert body["total"] == 23


def test_test_endpoint_junit():
    r = client.post("/test?format=junit", json={"xml": _load("good.xml")})
    assert r.status_code == 200
    assert "<testsuite" in r.text


def test_batch():
    r = client.post("/test/batch", json={"invoices": [
        {"name": "good", "xml": _load("good.xml")},
        {"name": "bad", "xml": _load("bad.xml")},
    ]})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 46  # 23 scenarios x 2 invoices


def test_validate_malformed_returns_400():
    r = client.post("/validate", json={"xml": "<Invoice><oops></Invoice>"})
    assert r.status_code == 400


def test_test_endpoint_persists_a_run():
    r = client.post("/test", json={"xml": _load("good.xml")})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert run_id is not None

    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["mode"] == "single"
    assert body["total"] == 23
    assert len(body["results"]) == 23


def test_batch_endpoint_persists_a_run():
    r = client.post("/test/batch", json={"invoices": [
        {"name": "good", "xml": _load("good.xml")},
        {"name": "bad", "xml": _load("bad.xml")},
    ]})
    run_id = r.json()["run_id"]
    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["mode"] == "batch"
    assert detail.json()["invoice_count"] == 2


def test_runs_list_most_recent_first():
    client.post("/test", json={"xml": _load("good.xml")})
    r1 = client.post("/test", json={"xml": _load("good.xml")})
    r = client.get("/runs?limit=5")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) >= 2
    assert runs[0]["id"] == r1.json()["run_id"]  # most recent first


def test_run_detail_404_for_missing():
    r = client.get("/runs/999999")
    assert r.status_code == 404


def test_stats_endpoint_reflects_recorded_runs():
    client.post("/test", json={"xml": _load("bad.xml")})
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_runs"] >= 1
    assert body["total_scenarios_executed"] >= 23
    assert "heuristic" in body["by_validator"]


def test_health_reports_history_capability():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["history"] is True
