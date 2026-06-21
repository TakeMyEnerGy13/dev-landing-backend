# Dev Landing Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI backend for a developer landing page that handles a contact form end-to-end: validate → AI-analyze → email (background) → respond, with rate limiting, file logging, metrics, graceful AI fallback, and a static landing page.

**Architecture:** Layered — Controllers (`api/`) handle HTTP only; Services (`services/`) hold business logic; Handlers/Repositories (`handlers/`) own file/in-memory storage and external I/O. A request-logging middleware and a global exception handler wrap everything. AI uses one Claude call with structured JSON output and a rule-based fallback. Email sends run in FastAPI `BackgroundTasks` so the HTTP response is not blocked on SMTP.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Pydantic v2 + pydantic-settings, `anthropic` SDK, `aiosmtplib`, `pytest` + `pytest-asyncio` + `httpx`.

## Global Constraints

- Python **3.11+**.
- All config comes from environment / `.env` via `pydantic-settings` — **no hardcoded secrets, URLs, or thresholds**.
- Service must start and serve requests **with an empty `.env`** (no `ANTHROPIC_API_KEY`, no SMTP creds) — AI and email degrade gracefully, never crash on import or request.
- Layer rule: `api/` never imports `aiosmtplib`/`anthropic`/file IO directly; `services/` never imports `fastapi`; `handlers/` never imports business rules.
- All log output is **JSON lines** written to files under `data/` (gitignored), created on startup.
- AI model is read from `AI_MODEL` (default `claude-haiku-4-5`). AI call uses `output_config={"format": {"type": "json_schema", "schema": ...}}` — never assistant prefill, never `tool_use` parsing.
- Rate limit: in-memory sliding window, `asyncio.Lock`-guarded, threshold from env (`RATE_LIMIT_MAX`, `RATE_LIMIT_WINDOW_SECONDS`).
- Every test runs with monkeypatched email + AI (no real network in the suite).

---

### Task 1: Project scaffold, config, and app entrypoint

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_health.py`

**Interfaces:**
- Produces: `app.config.Settings` (pydantic-settings) with fields: `anthropic_api_key: str | None`, `ai_model: str = "claude-haiku-4-5"`, `ai_timeout_seconds: float = 12.0`, `owner_email: str = "owner@example.com"`, `smtp_host: str | None`, `smtp_port: int = 587`, `smtp_user: str | None`, `smtp_password: str | None`, `mail_from: str = "noreply@devlanding.local"`, `rate_limit_max: int = 5`, `rate_limit_window_seconds: int = 600`, `cors_origins: str = "*"`, `data_dir: str = "data"`. Exposes `get_settings()` returning a cached `Settings`.
- Produces: `app.main.create_app() -> FastAPI` and module-level `app = create_app()`.
- Produces: `GET /api/health` returning `{"status": "ok", "uptime_seconds": float, "ai_available": bool, "email_configured": bool}`.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.0
anthropic==0.69.0
aiosmtplib==3.0.2
pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
```

- [ ] **Step 2: Write `.env.example`**

```
# AI (optional — service runs without it via fallback)
ANTHROPIC_API_KEY=
AI_MODEL=claude-haiku-4-5
AI_TIMEOUT_SECONDS=12

# Email (Mailtrap sandbox recommended for the demo)
OWNER_EMAIL=owner@example.com
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
MAIL_FROM=noreply@devlanding.local

# Rate limiting
RATE_LIMIT_MAX=5
RATE_LIMIT_WINDOW_SECONDS=600

# CORS (comma-separated origins, or * for all)
CORS_ORIGINS=*

# Storage
DATA_DIR=data
```

- [ ] **Step 3: Write `app/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = None
    ai_model: str = "claude-haiku-4-5"
    ai_timeout_seconds: float = 12.0

    owner_email: str = "owner@example.com"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "noreply@devlanding.local"

    rate_limit_max: int = 5
    rate_limit_window_seconds: int = 600

    cors_origins: str = "*"
    data_dir: str = "data"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Write `app/__init__.py` and `tests/__init__.py`** (both empty files)

- [ ] **Step 5: Write `app/main.py` (health only for now)**

```python
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

_START_TIME = time.monotonic()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Dev Landing Backend", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "uptime_seconds": round(time.monotonic() - _START_TIME, 3),
            "ai_available": settings.ai_configured,
            "email_configured": settings.email_configured,
        }

    return app


app = create_app()
```

- [ ] **Step 6: Write `tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
```

- [ ] **Step 7: Write `tests/test_health.py`**

```python
def test_health_returns_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body
    assert "ai_available" in body
    assert "email_configured" in body
```

- [ ] **Step 8: Install deps and run the test**

Run: `pip install -r requirements.txt && pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .env.example app/ tests/
git commit -m "feat: project scaffold, settings, health endpoint"
```

---

### Task 2: Structured JSON logging to file

**Files:**
- Create: `app/core/__init__.py`
- Create: `app/core/logging.py`
- Create: `tests/test_logging.py`

**Interfaces:**
- Consumes: `app.config.get_settings()` for `data_dir`.
- Produces: `app.core.logging.setup_logging() -> None` (configures two file handlers), `get_request_logger() -> logging.Logger` (name `"requests"`, writes to `data/requests.log`), `get_app_logger() -> logging.Logger` (name `"app"`, writes to `data/app.log`). Both emit one JSON object per line.

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from app.core.logging import setup_logging, get_request_logger


def test_request_logger_writes_json_line(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()

    setup_logging()
    logger = get_request_logger()
    logger.info("", extra={"event": {"method": "POST", "path": "/api/contact", "status": 200}})

    for h in logger.handlers:
        h.flush()
    line = Path(tmp_path, "requests.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["method"] == "POST"
    assert record["path"] == "/api/contact"
    assert record["status"] == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_logging.py -v`
Expected: FAIL (module `app.core.logging` not found).

- [ ] **Step 3: Write `app/core/__init__.py`** (empty)

- [ ] **Step 4: Write `app/core/logging.py`**

```python
import json
import logging
from pathlib import Path

from app.config import get_settings

_CONFIGURED = False


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)
        elif record.getMessage():
            payload["message"] = record.getMessage()
        return json.dumps(payload, ensure_ascii=False)


def _build_logger(name: str, filename: str) -> logging.Logger:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    handler = logging.FileHandler(data_dir / filename, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    return logger


def setup_logging() -> None:
    global _CONFIGURED
    _build_logger("requests", "requests.log")
    _build_logger("app", "app.log")
    _CONFIGURED = True


def get_request_logger() -> logging.Logger:
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger("requests")


def get_app_logger() -> logging.Logger:
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger("app")
```

- [ ] **Step 5: Run the test**

Run: `pytest tests/test_logging.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/__init__.py app/core/logging.py tests/test_logging.py
git commit -m "feat: JSON-line file logging for requests and app events"
```

---

### Task 3: Custom errors and global exception handler

**Files:**
- Create: `app/core/errors.py`
- Modify: `app/main.py` (register handlers)
- Create: `tests/test_errors.py`

**Interfaces:**
- Produces: exception classes in `app.core.errors`: `AppError(Exception)` with `status_code: int` and `message: str`; subclasses `RateLimitExceeded(retry_after: int)` (429), `AIServiceError` (502), `EmailDeliveryError` (502).
- Produces: `register_exception_handlers(app: FastAPI) -> None` mapping `AppError` and uncaught `Exception` to JSON `{"error": str, "detail": str, "request_id": str}` with the right status; `RateLimitExceeded` adds a `Retry-After` header. Reads `request.state.request_id` (set by middleware in Task 4; falls back to `"-"`).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_errors.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/core/errors.py`**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_app_logger


class AppError(Exception):
    status_code: int = 500
    message: str = "Application error"

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class RateLimitExceeded(AppError):
    status_code = 429
    message = "Rate limit exceeded. Please try again later."

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(self.message)


class AIServiceError(AppError):
    status_code = 502
    message = "AI service is temporarily unavailable."


class EmailDeliveryError(AppError):
    status_code = 502
    message = "Failed to deliver email notification."


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitExceeded):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "detail": exc.message, "request_id": _request_id(request)},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        get_app_logger().error(
            "",
            extra={"event": {"kind": "unhandled_exception", "type": type(exc).__name__,
                             "detail": str(exc), "request_id": _request_id(request)}},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": "Internal server error",
                     "request_id": _request_id(request)},
        )
```

- [ ] **Step 4: Register in `app/main.py`** — add the import and call inside `create_app`, after CORS:

```python
from app.core.errors import register_exception_handlers
```

and inside `create_app`, after `app.add_middleware(...)`:

```python
    register_exception_handlers(app)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_errors.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/errors.py app/main.py tests/test_errors.py
git commit -m "feat: custom errors and global exception handler"
```

---

### Task 4: Request-logging middleware (request_id + latency)

**Files:**
- Create: `app/core/middleware.py`
- Modify: `app/main.py` (register middleware)
- Create: `tests/test_middleware.py`

**Interfaces:**
- Consumes: `get_request_logger()` from Task 2.
- Produces: `RequestLoggingMiddleware` (Starlette `BaseHTTPMiddleware`). Assigns `request.state.request_id = uuid4().hex`, measures latency, writes one JSON line to `requests.log` with `request_id, method, path, ip, status, latency_ms`, and sets response header `X-Request-ID`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_middleware.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/core/middleware.py`**

```python
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_request_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        client_ip = request.client.host if request.client else "-"
        get_request_logger().info(
            "",
            extra={"event": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "ip": client_ip,
                "status": response.status_code,
                "latency_ms": latency_ms,
            }},
        )
        response.headers["X-Request-ID"] = request_id
        return response
```

- [ ] **Step 4: Register in `app/main.py`** — add import:

```python
from app.core.middleware import RequestLoggingMiddleware
```

and inside `create_app`, **before** the CORS middleware (so logging wraps outermost), add:

```python
    app.add_middleware(RequestLoggingMiddleware)
```

Also call `setup_logging()` at the top of `create_app`:

```python
    from app.core.logging import setup_logging
    setup_logging()
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_middleware.py tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/middleware.py app/main.py tests/test_middleware.py
git commit -m "feat: request-logging middleware with request_id and latency"
```

---

### Task 5: Pydantic schemas (contact + AI analysis)

**Files:**
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/contact.py`
- Create: `app/schemas/ai.py`
- Create: `tests/test_schemas.py`

**Interfaces:**
- Produces: `app.schemas.contact.ContactRequest` with validated fields `name`, `email`, `phone`, `comment`, optional `honeypot`; `ContactResponse(success: bool, message: str, analysis: AIAnalysis)`.
- Produces: `app.schemas.ai.AIAnalysis` with `sentiment: Literal["positive","neutral","negative"]`, `category: Literal["sales","support","spam","other"]`, `priority: Literal["low","normal","high"]`, `suggested_reply: str`, `ai_available: bool`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pydantic import ValidationError

from app.schemas.contact import ContactRequest


def test_valid_contact_request():
    req = ContactRequest(
        name="  Alice  ", email="alice@example.com",
        phone="+1 555 123 4567", comment="I would like to discuss a project.",
    )
    assert req.name == "Alice"          # trimmed
    assert req.honeypot is None


@pytest.mark.parametrize("field,value", [
    ("name", "A"),                       # too short
    ("email", "not-an-email"),
    ("phone", "abc"),                    # no digits
    ("comment", "hi"),                   # too short
])
def test_invalid_fields_raise(field, value):
    data = {"name": "Alice", "email": "alice@example.com",
            "phone": "+15551234567", "comment": "A valid comment here."}
    data[field] = value
    with pytest.raises(ValidationError):
        ContactRequest(**data)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_schemas.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/schemas/__init__.py`** (empty)

- [ ] **Step 4: Write `app/schemas/ai.py`**

```python
from typing import Literal

from pydantic import BaseModel

Sentiment = Literal["positive", "neutral", "negative"]
Category = Literal["sales", "support", "spam", "other"]
Priority = Literal["low", "normal", "high"]


class AIAnalysis(BaseModel):
    sentiment: Sentiment
    category: Category
    priority: Priority
    suggested_reply: str
    ai_available: bool = True
```

- [ ] **Step 5: Write `app/schemas/contact.py`**

```python
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.ai import AIAnalysis

_PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")


class ContactRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    comment: str = Field(min_length=5, max_length=2000)
    # Permissive: a non-empty value is accepted here and treated as spam in ContactService.
    honeypot: str | None = Field(default=None)

    @field_validator("name", "comment")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("phone")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        v = v.strip()
        if not _PHONE_RE.match(v) or not any(c.isdigit() for c in v):
            raise ValueError("invalid phone number")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "name": "Alice Founder",
                "email": "alice@example.com",
                "phone": "+1 555 123 4567",
                "comment": "Loved your portfolio — can we discuss a paid project?",
            }]
        }
    }


class ContactResponse(BaseModel):
    success: bool
    message: str
    analysis: AIAnalysis
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_schemas.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/ tests/test_schemas.py
git commit -m "feat: pydantic schemas for contact request, response, and AI analysis"
```

---

### Task 6: In-memory rate limiter

**Files:**
- Create: `app/handlers/__init__.py`
- Create: `app/handlers/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

**Interfaces:**
- Produces: `app.handlers.rate_limiter.RateLimiter(max_requests: int, window_seconds: int)` with `async def check(self, key: str) -> None` that raises `RateLimitExceeded(retry_after)` when the key exceeds `max_requests` within the sliding window. Internally `dict[str, list[float]]` guarded by `asyncio.Lock`, pruning timestamps older than the window.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.core.errors import RateLimitExceeded
from app.handlers.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_requests=3, window_seconds=600)
    for _ in range(3):
        await limiter.check("1.2.3.4")
    with pytest.raises(RateLimitExceeded) as exc:
        await limiter.check("1.2.3.4")
    assert exc.value.retry_after > 0


@pytest.mark.asyncio
async def test_separate_keys_independent():
    limiter = RateLimiter(max_requests=1, window_seconds=600)
    await limiter.check("a")
    await limiter.check("b")  # different key — must not raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_rate_limiter.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/handlers/__init__.py`** (empty)

- [ ] **Step 4: Write `app/handlers/rate_limiter.py`**

```python
import asyncio
import time

from app.core.errors import RateLimitExceeded


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            timestamps = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(timestamps) >= self._max:
                retry_after = int(timestamps[0] + self._window - now) + 1
                self._hits[key] = timestamps
                raise RateLimitExceeded(retry_after=max(retry_after, 1))
            timestamps.append(now)
            self._hits[key] = timestamps
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_rate_limiter.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/handlers/__init__.py app/handlers/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat: in-memory sliding-window rate limiter"
```

---

### Task 7: Metrics store (atomic JSON file)

**Files:**
- Create: `app/handlers/metrics_store.py`
- Create: `tests/test_metrics_store.py`

**Interfaces:**
- Produces: `app.handlers.metrics_store.MetricsStore(path: str)` with `async def increment(self, category: str, sentiment: str) -> None` and `def snapshot(self) -> dict` returning `{"total": int, "by_category": dict, "by_sentiment": dict, "last_updated": str | None}`. Writes atomically (temp file + `os.replace`). `asyncio.Lock`-guarded writes.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.handlers.metrics_store import MetricsStore


@pytest.mark.asyncio
async def test_increment_and_snapshot(tmp_path):
    store = MetricsStore(str(tmp_path / "metrics.json"))
    await store.increment("sales", "positive")
    await store.increment("sales", "negative")
    snap = store.snapshot()
    assert snap["total"] == 2
    assert snap["by_category"]["sales"] == 2
    assert snap["by_sentiment"]["positive"] == 1
    assert snap["last_updated"] is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_metrics_store.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/handlers/metrics_store.py`**

```python
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class MetricsStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"total": 0, "by_category": {}, "by_sentiment": {}, "last_updated": None})

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"total": 0, "by_category": {}, "by_sentiment": {}, "last_updated": None}

    def _write(self, data: dict) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    async def increment(self, category: str, sentiment: str) -> None:
        async with self._lock:
            data = self._read()
            data["total"] += 1
            data["by_category"][category] = data["by_category"].get(category, 0) + 1
            data["by_sentiment"][sentiment] = data["by_sentiment"].get(sentiment, 0) + 1
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._write(data)

    def snapshot(self) -> dict:
        return self._read()
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/test_metrics_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/handlers/metrics_store.py tests/test_metrics_store.py
git commit -m "feat: atomic file-backed metrics store"
```

---

### Task 8: AI service (Claude structured output + rule-based fallback)

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/ai_service.py`
- Create: `tests/test_ai_service.py`

**Interfaces:**
- Consumes: `app.config.Settings`, `app.schemas.ai.AIAnalysis`.
- Produces: `app.services.ai_service.AIService(settings: Settings, client=None)` with `async def analyze(self, comment: str) -> AIAnalysis`. When `settings.ai_configured` is False or the Claude call raises/returns invalid JSON, returns a rule-based `AIAnalysis(ai_available=False)`. On success returns `AIAnalysis(ai_available=True)`.
- Produces: module-level `ANALYSIS_SCHEMA` (dict), `SYSTEM_PROMPT` (str), `rule_based_fallback(comment: str) -> AIAnalysis`.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.config import Settings
from app.services.ai_service import AIService, rule_based_fallback


@pytest.mark.asyncio
async def test_fallback_used_when_no_api_key():
    svc = AIService(Settings(anthropic_api_key=None))
    result = await svc.analyze("This is URGENT, please respond ASAP about a job.")
    assert result.ai_available is False
    assert result.priority == "high"          # keyword "urgent"/"asap"
    assert result.category == "sales"         # keyword "job"


@pytest.mark.asyncio
async def test_fallback_on_client_error():
    class BoomClient:
        class messages:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("network down")

    svc = AIService(Settings(anthropic_api_key="sk-test"), client=BoomClient())
    result = await svc.analyze("Hello, nice site.")
    assert result.ai_available is False


def test_rule_based_neutral_default():
    result = rule_based_fallback("Just saying hi.")
    assert result.sentiment == "neutral"
    assert result.ai_available is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_ai_service.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/services/__init__.py`** (empty)

- [ ] **Step 4: Write `app/services/ai_service.py`**

```python
import json

from app.config import Settings
from app.core.logging import get_app_logger
from app.schemas.ai import AIAnalysis

SYSTEM_PROMPT = (
    "You are an assistant that triages inbound messages from a developer's "
    "landing page contact form. Analyze the user's message and return the "
    "sentiment, the request category, a priority, and a short, polite draft "
    "reply in the same language as the message. Do not invent facts about the "
    "site owner. Keep the draft reply under 80 words."
)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "category": {"type": "string", "enum": ["sales", "support", "spam", "other"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        "suggested_reply": {"type": "string"},
    },
    "required": ["sentiment", "category", "priority", "suggested_reply"],
    "additionalProperties": False,
}

_HIGH_PRIORITY = ("urgent", "asap", "срочно", "немедленно")
_SALES = ("project", "hire", "job", "collaborat", "vacancy", "проект", "сотруднич", "ваканс")
_NEGATIVE = ("bad", "terrible", "awful", "broken", "disappoint", "плохо", "ужас")


def rule_based_fallback(comment: str) -> AIAnalysis:
    text = comment.lower()
    priority = "high" if any(k in text for k in _HIGH_PRIORITY) else "normal"
    category = "sales" if any(k in text for k in _SALES) else "other"
    sentiment = "negative" if any(k in text for k in _NEGATIVE) else "neutral"
    return AIAnalysis(
        sentiment=sentiment,
        category=category,
        priority=priority,
        suggested_reply="Thank you for reaching out — I will review your message and get back to you shortly.",
        ai_available=False,
    )


class AIService:
    def __init__(self, settings: Settings, client=None):
        self._settings = settings
        self._client = client
        if self._client is None and settings.ai_configured:
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.ai_timeout_seconds,
            )

    async def analyze(self, comment: str) -> AIAnalysis:
        if self._client is None:
            return rule_based_fallback(comment)
        try:
            resp = await self._client.messages.create(
                model=self._settings.ai_model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": comment}],
                output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
            )
            text = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(text)
            return AIAnalysis(**data, ai_available=True)
        except Exception as exc:  # noqa: BLE001 — any failure must degrade gracefully
            get_app_logger().warning(
                "", extra={"event": {"kind": "ai_fallback", "type": type(exc).__name__, "detail": str(exc)}}
            )
            return rule_based_fallback(comment)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_ai_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/__init__.py app/services/ai_service.py tests/test_ai_service.py
git commit -m "feat: AI service with structured Claude output and rule-based fallback"
```

---

### Task 9: Email service (aiosmtplib, two messages)

**Files:**
- Create: `app/services/email_service.py`
- Create: `tests/test_email_service.py`

**Interfaces:**
- Consumes: `app.config.Settings`, `app.schemas.contact.ContactRequest`, `app.schemas.ai.AIAnalysis`.
- Produces: `app.services.email_service.EmailService(settings: Settings, sender=None)` with `async def send_owner(self, data: ContactRequest, analysis: AIAnalysis) -> None` and `async def send_user_copy(self, data: ContactRequest) -> None`. `sender` is an injectable async callable `(message: EmailMessage) -> None`; default uses `aiosmtplib.send`. If `settings.email_configured` is False, logs and returns (no crash). Failures are logged to `app.log`, never raised into the request path.
- Produces: helper `build_owner_message(...)`/`build_user_message(...)` returning `email.message.EmailMessage` with escaped values.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.config import Settings
from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest
from app.services.email_service import EmailService


def _req() -> ContactRequest:
    return ContactRequest(name="Alice", email="alice@example.com",
                          phone="+15551234567", comment="Hello there.")


def _analysis() -> AIAnalysis:
    return AIAnalysis(sentiment="positive", category="sales", priority="high",
                      suggested_reply="Thanks!", ai_available=True)


@pytest.mark.asyncio
async def test_owner_and_user_messages_sent():
    sent = []

    async def fake_sender(message):
        sent.append(message)

    svc = EmailService(
        Settings(smtp_host="h", smtp_user="u", smtp_password="p", owner_email="owner@x.com"),
        sender=fake_sender,
    )
    await svc.send_owner(_req(), _analysis())
    await svc.send_user_copy(_req())

    assert len(sent) == 2
    assert sent[0]["To"] == "owner@x.com"
    assert sent[1]["To"] == "alice@example.com"


@pytest.mark.asyncio
async def test_unconfigured_email_is_noop():
    called = False

    async def fake_sender(message):
        nonlocal called
        called = True

    svc = EmailService(Settings(smtp_host=None), sender=fake_sender)
    await svc.send_owner(_req(), _analysis())
    assert called is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_email_service.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/services/email_service.py`**

```python
from email.message import EmailMessage
from html import escape

from app.config import Settings
from app.core.logging import get_app_logger
from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest


def build_owner_message(settings: Settings, data: ContactRequest, analysis: AIAnalysis) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = settings.owner_email
    msg["Subject"] = f"New contact [{analysis.priority}] from {data.name}"
    msg.set_content(
        f"Name: {data.name}\nEmail: {data.email}\nPhone: {data.phone}\n\n"
        f"Message:\n{data.comment}\n\n"
        f"--- AI analysis (available={analysis.ai_available}) ---\n"
        f"Sentiment: {analysis.sentiment}\nCategory: {analysis.category}\n"
        f"Priority: {analysis.priority}\n\nSuggested reply:\n{analysis.suggested_reply}"
    )
    return msg


def build_user_message(settings: Settings, data: ContactRequest) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = data.email
    msg["Subject"] = "We received your message"
    msg.set_content(
        f"Hi {data.name},\n\nThanks for reaching out — we received your message "
        f"and will reply soon.\n\nYour message:\n{data.comment}\n\n— The team"
    )
    return msg


class EmailService:
    def __init__(self, settings: Settings, sender=None):
        self._settings = settings
        self._sender = sender or self._default_sender

    async def _default_sender(self, message: EmailMessage) -> None:
        import aiosmtplib
        await aiosmtplib.send(
            message,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_user,
            password=self._settings.smtp_password,
            start_tls=True,
        )

    async def _send(self, message: EmailMessage, kind: str) -> None:
        if not self._settings.email_configured:
            get_app_logger().info("", extra={"event": {"kind": "email_skipped", "reason": "not_configured", "mail": kind}})
            return
        try:
            await self._sender(message)
            get_app_logger().info("", extra={"event": {"kind": "email_sent", "mail": kind, "to": message["To"]}})
        except Exception as exc:  # noqa: BLE001 — never break the request on email failure
            get_app_logger().error("", extra={"event": {"kind": "email_failed", "mail": kind, "type": type(exc).__name__, "detail": str(exc)}})

    async def send_owner(self, data: ContactRequest, analysis: AIAnalysis) -> None:
        await self._send(build_owner_message(self._settings, data, analysis), "owner")

    async def send_user_copy(self, data: ContactRequest) -> None:
        await self._send(build_user_message(self._settings, data), "user_copy")
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_email_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/email_service.py tests/test_email_service.py
git commit -m "feat: email service with owner + user-copy messages and safe failures"
```

---

### Task 10: Contact orchestration service

**Files:**
- Create: `app/services/contact_service.py`
- Create: `tests/test_contact_service.py`

**Interfaces:**
- Consumes: `AIService`, `EmailService`, `MetricsStore`, `ContactRequest`, `AIAnalysis`.
- Produces: `app.services.contact_service.ContactService(ai, email, metrics)` with `async def handle(self, data: ContactRequest, schedule) -> AIAnalysis`. `schedule` is a callable `(coro_fn, *args)` (FastAPI `BackgroundTasks.add_task`). If `data.honeypot` is non-empty, returns a benign spam `AIAnalysis` immediately without AI/email/metrics. Otherwise: runs AI, schedules `email.send_owner` and `email.send_user_copy` as background tasks, increments metrics, returns the analysis.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest
from app.services.contact_service import ContactService


class FakeAI:
    async def analyze(self, comment):
        return AIAnalysis(sentiment="positive", category="sales", priority="high",
                          suggested_reply="ok", ai_available=True)


class FakeEmail:
    async def send_owner(self, data, analysis): ...
    async def send_user_copy(self, data): ...


class FakeMetrics:
    def __init__(self): self.calls = []
    async def increment(self, category, sentiment): self.calls.append((category, sentiment))


def _req(honeypot=None):
    return ContactRequest(name="Alice", email="a@x.com", phone="+15551234567",
                          comment="Let us talk.", honeypot=honeypot)


@pytest.mark.asyncio
async def test_happy_path_schedules_emails_and_metrics():
    scheduled = []
    metrics = FakeMetrics()
    svc = ContactService(FakeAI(), FakeEmail(), metrics)

    analysis = await svc.handle(_req(), schedule=lambda fn, *a: scheduled.append((fn, a)))

    assert analysis.ai_available is True
    assert len(scheduled) == 2                       # owner + user copy
    assert metrics.calls == [("sales", "positive")]


@pytest.mark.asyncio
async def test_honeypot_short_circuits():
    scheduled = []
    metrics = FakeMetrics()
    svc = ContactService(FakeAI(), FakeEmail(), metrics)

    analysis = await svc.handle(_req(honeypot="i-am-a-bot"),
                                schedule=lambda fn, *a: scheduled.append((fn, a)))

    assert analysis.category == "spam"
    assert scheduled == []
    assert metrics.calls == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_contact_service.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write `app/services/contact_service.py`**

```python
from app.schemas.ai import AIAnalysis
from app.schemas.contact import ContactRequest


class ContactService:
    def __init__(self, ai, email, metrics):
        self._ai = ai
        self._email = email
        self._metrics = metrics

    async def handle(self, data: ContactRequest, schedule) -> AIAnalysis:
        if data.honeypot:
            return AIAnalysis(
                sentiment="neutral", category="spam", priority="low",
                suggested_reply="", ai_available=False,
            )

        analysis = await self._ai.analyze(data.comment)
        schedule(self._email.send_owner, data, analysis)
        schedule(self._email.send_user_copy, data)
        await self._metrics.increment(analysis.category, analysis.sentiment)
        return analysis
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_contact_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/contact_service.py tests/test_contact_service.py
git commit -m "feat: contact orchestration service with honeypot short-circuit"
```

---

### Task 11: API wiring — dependencies, contact/metrics routes, OpenAPI polish

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/dependencies.py`
- Create: `app/api/contact.py`
- Create: `app/api/metrics.py`
- Modify: `app/main.py` (include routers, move health into a router optional)
- Create: `tests/test_contact_endpoint.py`

**Interfaces:**
- Produces: `app.dependencies` singletons — `get_rate_limiter()`, `get_metrics_store()`, `get_ai_service()`, `get_email_service()`, `get_contact_service()` — all built from `get_settings()` and cached at module load.
- Produces: `app.api.contact.router` with `POST /api/contact` (response model `ContactResponse`, documented 422/429 responses) and `app.api.metrics.router` with `GET /api/metrics`.
- Endpoint flow: `rate_limiter.check(client_ip)` → FastAPI validates `ContactRequest` (422 on failure) → `contact_service.handle(data, background_tasks.add_task)` → `200 ContactResponse`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_contact_endpoint.py -v`
Expected: FAIL (modules not found).

- [ ] **Step 3: Write `app/api/__init__.py`** (empty)

- [ ] **Step 4: Write `app/dependencies.py`**

```python
from app.config import get_settings
from app.handlers.metrics_store import MetricsStore
from app.handlers.rate_limiter import RateLimiter
from app.services.ai_service import AIService
from app.services.contact_service import ContactService
from app.services.email_service import EmailService

_rate_limiter: RateLimiter | None = None
_metrics_store: MetricsStore | None = None
_ai_service: AIService | None = None
_email_service: EmailService | None = None
_contact_service: ContactService | None = None


def reset() -> None:
    """Rebuild all singletons (used by tests after changing settings)."""
    global _rate_limiter, _metrics_store, _ai_service, _email_service, _contact_service
    _rate_limiter = _metrics_store = _ai_service = _email_service = _contact_service = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        s = get_settings()
        _rate_limiter = RateLimiter(s.rate_limit_max, s.rate_limit_window_seconds)
    return _rate_limiter


def get_metrics_store() -> MetricsStore:
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = MetricsStore(f"{get_settings().data_dir}/metrics.json")
    return _metrics_store


def get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService(get_settings())
    return _ai_service


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService(get_settings())
    return _email_service


def get_contact_service() -> ContactService:
    global _contact_service
    if _contact_service is None:
        _contact_service = ContactService(get_ai_service(), get_email_service(), get_metrics_store())
    return _contact_service
```

- [ ] **Step 5: Write `app/api/contact.py`**

```python
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.dependencies import get_contact_service, get_rate_limiter
from app.handlers.rate_limiter import RateLimiter
from app.schemas.contact import ContactRequest, ContactResponse
from app.services.contact_service import ContactService

router = APIRouter(prefix="/api", tags=["contact"])


@router.post(
    "/contact",
    response_model=ContactResponse,
    summary="Submit the contact form",
    description="Validates input, runs AI triage, schedules email notifications "
                "(owner + user copy) in the background, and returns the AI analysis.",
    responses={
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def submit_contact(
    payload: ContactRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    limiter: RateLimiter = Depends(get_rate_limiter),
    service: ContactService = Depends(get_contact_service),
) -> ContactResponse:
    client_ip = request.client.host if request.client else "-"
    await limiter.check(client_ip)
    analysis = await service.handle(payload, schedule=background_tasks.add_task)
    return ContactResponse(
        success=True,
        message="Thanks! Your message was received.",
        analysis=analysis,
    )
```

- [ ] **Step 6: Write `app/api/metrics.py`**

```python
from fastapi import APIRouter, Depends

from app.dependencies import get_metrics_store
from app.handlers.metrics_store import MetricsStore

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", summary="Aggregated contact statistics")
async def metrics(store: MetricsStore = Depends(get_metrics_store)) -> dict:
    return store.snapshot()
```

- [ ] **Step 7: Wire routers into `app/main.py`** — add imports and `include_router` calls inside `create_app` after `register_exception_handlers`:

```python
    from app.api import contact, metrics
    app.include_router(contact.router)
    app.include_router(metrics.router)
```

- [ ] **Step 8: Run the tests**

Run: `pytest tests/test_contact_endpoint.py -v`
Expected: PASS.

- [ ] **Step 9: Run the full suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add app/api/ app/dependencies.py app/main.py tests/test_contact_endpoint.py
git commit -m "feat: contact and metrics endpoints with rate limiting and DI"
```

---

### Task 12: Static landing page served by FastAPI

**Files:**
- Create: `app/static/index.html`
- Create: `app/static/style.css`
- Create: `app/static/app.js`
- Modify: `app/main.py` (mount static, serve index at `/`)
- Create: `tests/test_static.py`

**Interfaces:**
- Produces: `GET /` returns the landing HTML (200, `text/html`); `GET /static/style.css` served. The form posts JSON to `/api/contact` and renders the returned `analysis.sentiment` as a badge.

- [ ] **Step 1: Write the failing test**

```python
def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "contact" in resp.text.lower()
```

(Reuses the `client` fixture from `tests/conftest.py`.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_static.py -v`
Expected: FAIL (no `/` route).

- [ ] **Step 3: Write `app/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Alex Dev — Product Engineer</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <header class="hero">
    <h1>Alex Dev</h1>
    <p>Product engineer building AI-powered web apps.</p>
  </header>

  <section class="about">
    <h2>About</h2>
    <p>I ship full-stack products: TypeScript, Python, and Claude-powered features.</p>
  </section>

  <section class="contact">
    <h2>Contact</h2>
    <form id="contact-form">
      <input name="name" placeholder="Your name" required minlength="2" />
      <input name="email" type="email" placeholder="Email" required />
      <input name="phone" placeholder="Phone (+1 555 123 4567)" required />
      <textarea name="comment" placeholder="Your message" required minlength="5"></textarea>
      <!-- honeypot: hidden from humans, bots fill it -->
      <input class="hp" type="text" name="honeypot" tabindex="-1" autocomplete="off" />
      <button type="submit">Send</button>
    </form>
    <div id="result" class="result" hidden></div>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write `app/static/style.css`**

```css
:root { --bg:#0f1117; --fg:#e6e8ee; --accent:#6ea8fe; }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, sans-serif; background:var(--bg); color:var(--fg); }
.hero { padding:4rem 1.5rem 2rem; text-align:center; }
.hero h1 { font-size:2.5rem; margin:0; }
section { max-width:640px; margin:0 auto; padding:1.5rem; }
form { display:flex; flex-direction:column; gap:.75rem; }
input, textarea { padding:.7rem; border-radius:8px; border:1px solid #2a2f3a; background:#171a22; color:var(--fg); }
textarea { min-height:120px; resize:vertical; }
button { padding:.8rem; border:0; border-radius:8px; background:var(--accent); color:#0b0d12; font-weight:600; cursor:pointer; }
.hp { position:absolute; left:-9999px; }
.result { margin-top:1rem; padding:1rem; border-radius:8px; background:#171a22; }
.badge { display:inline-block; padding:.2rem .6rem; border-radius:999px; font-size:.8rem; }
.badge.positive { background:#1f6f43; } .badge.neutral { background:#4a5160; } .badge.negative { background:#7a2c2c; }
```

- [ ] **Step 5: Write `app/static/app.js`**

```javascript
const form = document.getElementById("contact-form");
const result = document.getElementById("result");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(form).entries());
  result.hidden = false;
  result.textContent = "Sending…";
  try {
    const res = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 429) { result.textContent = "Too many requests — please wait a bit."; return; }
    if (res.status === 422) { result.textContent = "Please check your inputs."; return; }
    const data = await res.json();
    const s = data.analysis.sentiment;
    result.innerHTML = `${data.message} <span class="badge ${s}">${s}</span>`;
    form.reset();
  } catch {
    result.textContent = "Network error — please try again.";
  }
});
```

- [ ] **Step 6: Mount static in `app/main.py`** — add imports and, inside `create_app` after routers:

```python
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_static.py -v`
Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add app/static/ app/main.py tests/test_static.py
git commit -m "feat: static landing page with contact form wired to the API"
```

---

### Task 13: Deploy config, Postman collection, and README

**Files:**
- Create: `render.yaml`
- Create: `postman_collection.json`
- Create: `README.md`

**Interfaces:** No code interfaces — packaging and documentation only.

- [ ] **Step 1: Write `render.yaml`**

```yaml
services:
  - type: web
    name: dev-landing-backend
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: AI_MODEL
        value: claude-haiku-4-5
      - key: OWNER_EMAIL
        sync: false
      - key: SMTP_HOST
        value: sandbox.smtp.mailtrap.io
      - key: SMTP_PORT
        value: "2525"
      - key: SMTP_USER
        sync: false
      - key: SMTP_PASSWORD
        sync: false
      - key: RATE_LIMIT_MAX
        value: "5"
      - key: RATE_LIMIT_WINDOW_SECONDS
        value: "600"
      - key: CORS_ORIGINS
        value: "*"
```

Note: Render may block SMTP port 587 — Mailtrap also accepts **2525**; `render.yaml` uses it.

- [ ] **Step 2: Write `postman_collection.json`**

```json
{
  "info": { "name": "Dev Landing Backend", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json" },
  "variable": [{ "key": "baseUrl", "value": "http://localhost:8000" }],
  "item": [
    {
      "name": "Health",
      "request": { "method": "GET", "url": "{{baseUrl}}/api/health" }
    },
    {
      "name": "Submit contact",
      "request": {
        "method": "POST",
        "header": [{ "key": "Content-Type", "value": "application/json" }],
        "url": "{{baseUrl}}/api/contact",
        "body": { "mode": "raw", "raw": "{\n  \"name\": \"Alice Founder\",\n  \"email\": \"alice@example.com\",\n  \"phone\": \"+1 555 123 4567\",\n  \"comment\": \"Loved your portfolio — can we discuss a paid project?\"\n}" }
      }
    },
    {
      "name": "Metrics",
      "request": { "method": "GET", "url": "{{baseUrl}}/api/metrics" }
    }
  ]
}
```

- [ ] **Step 3: Write `README.md`** covering all 7 required sections. Use this structure (fill each section with the project's real details):

```markdown
# Dev Landing Backend

FastAPI backend for a developer landing page: contact form with validation,
AI triage (Claude), email notifications, rate limiting, file logging, and metrics.

## 1. How to run

### Prerequisites
- Python 3.11+

### Install & run
\`\`\`bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in values (all optional — service runs without them)
uvicorn app.main:app --reload
\`\`\`
Open http://localhost:8000 (landing) and http://localhost:8000/docs (Swagger).

### Environment variables
| Var | Purpose | Default |
|-----|---------|---------|
| ANTHROPIC_API_KEY | Enables AI triage; omit to use rule-based fallback | (none) |
| AI_MODEL | Claude model id | claude-haiku-4-5 |
| OWNER_EMAIL | Recipient of owner notification | owner@example.com |
| SMTP_HOST/PORT/USER/PASSWORD | SMTP transport (Mailtrap sandbox recommended) | (none) |
| RATE_LIMIT_MAX / RATE_LIMIT_WINDOW_SECONDS | Sliding-window limit | 5 / 600 |
| CORS_ORIGINS | Comma-separated origins | * |

### Tests
\`\`\`bash
pytest -v
\`\`\`

## 2. Tech stack
- **Backend:** Python 3.11, FastAPI, Uvicorn, Pydantic v2, pydantic-settings
- **AI:** Anthropic Claude via `anthropic` SDK (structured JSON output)
- **Email:** aiosmtplib + Mailtrap sandbox
- **Tests:** pytest, pytest-asyncio, httpx

## 3. Architecture
Layered: Controllers (`app/api`) → Services (`app/services`) → Handlers/Repos (`app/handlers`).
- `core/` — logging, errors, middleware
- `schemas/` — Pydantic validation models
- `static/` — landing page
Explain the layer boundaries and why Python/FastAPI was chosen (auto-Swagger, Pydantic
validation, async I/O, proximity to a typed TS workflow).

## 4. API
Document `POST /api/contact`, `GET /api/health`, `GET /api/metrics` with request/response
examples and status codes (200/422/429). Point to `/docs` for the live OpenAPI.

## 5. AI integration
- One Claude call returns `{sentiment, category, priority, suggested_reply}` via
  `output_config.format` (json_schema) — guaranteed valid JSON.
- **Fallback:** no API key / timeout / error → rule-based keyword classifier, `ai_available=false`,
  request still returns 200. Include the system prompt text.

## 6. What was built with AI
Describe which parts were AI-generated, the prompts used, and what was corrected by hand.

## 7. Data storage
- `data/requests.log` — every request (JSON lines)
- `data/app.log` — errors and AI/email events
- `data/metrics.json` — aggregated stats (atomic writes)
- Rate limiting — in-memory sliding window (note: Redis in production)

## Deployment
Live URL: <fill in Render URL>. Note free-tier cold start (~30s first request).
\`\`\`
```

- [ ] **Step 4: Verify the app boots and OpenAPI renders**

Run: `uvicorn app.main:app --port 8000 &` then `curl -s http://localhost:8000/api/health` and `curl -s http://localhost:8000/openapi.json | python -c "import sys,json;json.load(sys.stdin)"`
Expected: health returns JSON; openapi.json parses without error. Stop the server afterward.

- [ ] **Step 5: Commit**

```bash
git add render.yaml postman_collection.json README.md
git commit -m "docs: README, Postman collection, and Render deploy config"
```

---

## Self-Review

**Spec coverage:**
- POST /api/contact + validation → Tasks 5, 11. ✓
- Email owner + user copy → Task 9. ✓
- Error handling + HTTP statuses → Tasks 3, 11. ✓
- Rate limiting → Tasks 6, 11. ✓
- Request logging to file → Tasks 2, 4. ✓
- AI integration + graceful fallback → Task 8. ✓
- /health, /metrics → Tasks 1, 7, 11. ✓
- .env / config → Task 1. ✓
- CORS → Task 1. ✓
- Swagger/OpenAPI (auto + custom descriptions/examples) → Tasks 5, 11. ✓
- Layered architecture → Tasks 8–11. ✓
- Honeypot → Tasks 5, 10. ✓
- Background email → Tasks 10, 11. ✓
- Frontend landing → Task 12. ✓
- README (7 sections), Postman, deploy → Task 13. ✓
- Empty-`.env` startup → covered by AIService/EmailService no-op paths (Tasks 8, 9) and the `ANTHROPIC_API_KEY=""` endpoint test (Task 11). ✓

**Placeholder scan:** No `TBD`/`TODO` and no traps. README section 6 is meant to be filled with real prompts after implementation — acceptable, it documents human work.

**Type consistency:** `AIAnalysis` fields (`sentiment/category/priority/suggested_reply/ai_available`) consistent across Tasks 5, 8, 9, 10, 11. `RateLimiter.check`, `MetricsStore.increment/snapshot`, `ContactService.handle(data, schedule)`, `EmailService.send_owner/send_user_copy` signatures match between definition and call sites.
