import pytest

from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")   # force AI fallback
    monkeypatch.setenv("RATE_LIMIT_MAX", "3")
    from app.config import get_settings
    get_settings.cache_clear()
    import app.dependencies as deps
    deps.reset()                                   # rebuild singletons with new settings
    return TestClient(create_app())


_VALID = {"name": "Alice", "email": "alice@example.com",
          "phone": "+15551234567", "comment": "I would love to hire you."}


def test_contact_happy_path(client):
    resp = client.post("/api/contact", json=_VALID)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["analysis"]["ai_available"] is False   # no API key → fallback
    assert body["analysis"]["category"] == "sales"


def test_contact_validation_error(client):
    bad = {**_VALID, "email": "nope"}
    resp = client.post("/api/contact", json=bad)
    assert resp.status_code == 422


def test_contact_rate_limited(client):
    for _ in range(3):
        assert client.post("/api/contact", json=_VALID).status_code == 200
    resp = client.post("/api/contact", json=_VALID)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_metrics_endpoint(client):
    client.post("/api/contact", json=_VALID)
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
