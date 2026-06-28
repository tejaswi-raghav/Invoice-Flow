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
    assert body["total"] == 16


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
    assert body["total"] == 32  # 16 scenarios x 2 invoices


def test_validate_malformed_returns_400():
    r = client.post("/validate", json={"xml": "<Invoice><oops></Invoice>"})
    assert r.status_code == 400
