from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError, RateLimitExceeded, register_exception_handlers


def _app_with_routes() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RateLimitExceeded(retry_after=42)

    @app.get("/unexpected")
    def unexpected():
        raise ValueError("kaboom")

    return app


def test_app_error_maps_to_status_and_header():
    client = TestClient(_app_with_routes(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "42"
    assert resp.json()["error"]
    assert "request_id" in resp.json()


def test_unexpected_error_maps_to_500_without_leaking():
    client = TestClient(_app_with_routes(), raise_server_exceptions=False)
    resp = client.get("/unexpected")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"
    assert "kaboom" not in resp.text
