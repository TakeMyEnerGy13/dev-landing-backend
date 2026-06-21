import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware


def test_middleware_logs_request_and_sets_header(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()
    setup_logging()

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"]

    line = Path(tmp_path, "requests.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["method"] == "GET"
    assert record["path"] == "/ping"
    assert record["status"] == 200
    assert "latency_ms" in record
    assert "request_id" in record
    assert "ip" in record
