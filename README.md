# Dev Landing Backend

FastAPI backend for a developer landing page: contact form with validation,
AI triage (Claude), email notifications, rate limiting, file logging, and metrics.

## 1. How to run

### Prerequisites
- Python 3.11+

### Install & run
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in values (all optional — service runs without them)
uvicorn app.main:app --reload
```
Open http://localhost:8000 (landing) and http://localhost:8000/docs (Swagger).

### Environment variables
| Var | Purpose | Default |
|-----|---------|---------|
| `ANTHROPIC_API_KEY` | Enables AI triage; omit to use rule-based fallback | (none) |
| `AI_MODEL` | Claude model id | `claude-haiku-4-5` |
| `AI_TIMEOUT_SECONDS` | Max seconds to wait for Claude response | `12.0` |
| `OWNER_EMAIL` | Recipient of owner notification email | `owner@example.com` |
| `SMTP_HOST` | SMTP server hostname (Mailtrap sandbox: `sandbox.smtp.mailtrap.io`) | (none) |
| `SMTP_PORT` | SMTP port — Render blocks 587, use **2525** with Mailtrap | `587` |
| `SMTP_USER` | SMTP username | (none) |
| `SMTP_PASSWORD` | SMTP password | (none) |
| `MAIL_FROM` | Sender address in notification emails | `noreply@devlanding.local` |
| `RATE_LIMIT_MAX` | Max requests per sliding window | `5` |
| `RATE_LIMIT_WINDOW_SECONDS` | Sliding-window size in seconds | `600` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `*` |
| `DATA_DIR` | Directory for log and metrics files | `data` |

All variables are optional. The service starts and responds correctly with an empty `.env`.

### Tests
```bash
pytest -v
```
25 tests, all green. Requires no live API keys — AI and email paths are mocked.

## 2. Tech stack
- **Backend:** Python 3.11, FastAPI, Uvicorn, Pydantic v2, pydantic-settings
- **AI:** Anthropic Claude via `anthropic` SDK — structured JSON output via `output_config.format` (json_schema)
- **Email:** aiosmtplib + Mailtrap sandbox (SMTP)
- **Validation:** Pydantic v2 field validators; `email-validator` for `EmailStr`
- **Tests:** pytest, pytest-asyncio, httpx (async test client)

## 3. Architecture

Layered: **Controllers** (`app/api/`) → **Services** (`app/services/`) → **Handlers** (`app/handlers/`).

```
app/
├── api/          # FastAPI routers — contact.py, metrics.py; health endpoint in main.py
├── services/     # Business logic — contact_service.py, ai_service.py, email_service.py
├── handlers/     # Infrastructure — rate_limiter.py, metrics_store.py, log_handler.py
├── schemas/      # Pydantic models — contact.py (request/response), ai.py (AIAnalysis)
├── core/         # Cross-cutting — logging.py (setup + structured logger), errors.py
│                 # (exception handlers), middleware.py (request logging middleware)
├── static/       # Static landing page (index.html, CSS, JS)
├── config.py     # pydantic-settings Settings with .env support
├── dependencies.py # FastAPI Depends factories (DI wiring)
└── main.py       # App factory — CORS, middleware, routers, static mount
data/             # Runtime-generated: *.log, metrics.json (git-ignored)
```

**Layer boundaries:**
- Routers know only request/response schemas and call one service method.
- Services orchestrate AI, email, and metrics; they do not import FastAPI.
- Handlers are pure I/O adapters (file writes, SMTP, in-memory state) with no business logic.

**Why FastAPI/Python:**
Auto-Swagger from type annotations means zero extra docs work. Pydantic v2 validation is the strictest in the ecosystem. `async`/`await` throughput fits background email dispatch. The typed approach mirrors a TS workflow, making context-switching low-friction.

## 4. API

Live interactive docs: http://localhost:8000/docs

### POST /api/contact

Submit the contact form. Validates input, runs AI triage, schedules email notifications in the background, returns analysis immediately.

**Request body (JSON):**
```json
{
  "name": "Alice Founder",
  "email": "alice@example.com",
  "phone": "+1 555 123 4567",
  "comment": "Loved your portfolio — can we discuss a paid project?",
  "honeypot": null
}
```
Field constraints: `name` 2–80 chars; `email` valid RFC 5322; `phone` 7–20 chars matching `^\+?[0-9 ()\-]{7,20}$`; `comment` 5–2000 chars. `honeypot` is optional — any non-null value silently marks the submission as spam (category `spam`, priority `low`) without returning an error.

**200 OK:**
```json
{
  "success": true,
  "message": "Thanks! Your message was received.",
  "analysis": {
    "sentiment": "positive",
    "category": "sales",
    "priority": "normal",
    "suggested_reply": "Thank you for reaching out! I'd love to discuss your project...",
    "ai_available": true
  }
}
```

**422 Unprocessable Entity** — Pydantic validation failure (missing field, bad email, phone out of range, etc.).

**429 Too Many Requests** — rate limit exceeded (default: 5 requests per 10 minutes per IP).

---

### GET /api/health

Returns service status and configuration flags.

**200 OK:**
```json
{
  "status": "ok",
  "uptime_seconds": 42.317,
  "ai_available": false,
  "email_configured": false
}
```

---

### GET /api/metrics

Returns aggregated submission counts.

**200 OK:**
```json
{
  "total": 12,
  "by_category": { "sales": 7, "support": 2, "spam": 1, "other": 2 },
  "by_priority": { "low": 1, "normal": 9, "high": 2 },
  "by_sentiment": { "positive": 6, "neutral": 4, "negative": 2 }
}
```

---

### GET /

Serves the static landing page (`app/static/index.html`).

### GET /docs

Auto-generated Swagger UI (FastAPI built-in).

## 5. AI integration

One Claude API call per contact submission returns a structured JSON object guaranteed by `output_config.format` (json_schema enforcement):

```json
{
  "sentiment": "positive" | "neutral" | "negative",
  "category":  "sales"    | "support" | "spam"    | "other",
  "priority":  "low"      | "normal"  | "high",
  "suggested_reply": "<string, ≤80 words, same language as message>"
}
```

**System prompt** (verbatim from `app/services/ai_service.py`):
```
You are an assistant that triages inbound messages from a developer's
landing page contact form. Analyze the user's message and return the
sentiment, the request category, a priority, and a short, polite draft
reply in the same language as the message. Do not invent facts about the
site owner. Keep the draft reply under 80 words.
```

**Graceful fallback** — triggered when:
- `ANTHROPIC_API_KEY` is not set
- Claude returns an error or times out (12 s default)

The fallback is a keyword-based rule engine (`rule_based_fallback` in `ai_service.py`). It matches keywords for priority (`urgent`, `asap`, `срочно`…), category (`project`, `hire`, `collaborat`…), and sentiment (`bad`, `terrible`, `ужас`…). The response always returns HTTP 200; `ai_available` is `false` in the analysis object when the fallback is used.

## 6. What was built with AI

The entire implementation — all source files and tests — was generated by Claude (Anthropic) sub-agents working from a detailed 13-task implementation plan (spec-driven TDD):

- **Generated by AI:** `app/` package (config, schemas, services, handlers, api routers, middleware, core utilities, static landing), `tests/` (25 pytest tests covering happy path, validation, rate limiting, AI fallback, email no-op, honeypot, metrics, logging), `requirements.txt`, `.env.example`, `render.yaml`, `postman_collection.json`.
- **Prompts used:** Each task had a brief in `.git/sdd/task-N-brief.md` describing exact file paths, interfaces, and expected test coverage. The sub-agents followed TDD: write tests → make them pass → self-review against spec.
- **Manual fixes:** Integration issues that required cross-task context: logging lifecycle (logger initialized before middleware fires), middleware ordering (CORS before RequestLogging), dependency injection wiring (`app/dependencies.py`), and `output_config` parameter shape for Claude's json_schema mode.
- **Oversight:** All 25 tests were verified green after each task; final integration was reviewed against the full spec checklist.

## 7. Data storage

All runtime data is written to `data/` (created automatically on first run; git-ignored).

| File | Format | Contents |
|------|--------|---------|
| `data/requests.log` | JSON Lines | One record per contact submission: timestamp, name, email (no password), IP, AI analysis result |
| `data/app.log` | JSON Lines | Application events: AI fallback warnings, email send results, errors |
| `data/metrics.json` | JSON object | Aggregated counters (total, by_category, by_priority, by_sentiment); written atomically via temp-file rename |

**Rate limiting** uses an in-memory sliding-window counter keyed by client IP. State is lost on restart. For production, replace with a Redis-backed counter (e.g., `redis-py` + `aioredis`).

## Deployment

No live hosted deployment exists yet. Follow the [local run instructions](#1-how-to-run) above to run the service on your machine.

### Optional: deploy to Render (free tier)

1. Fork/push this repo to GitHub.
2. In the [Render dashboard](https://render.com), create a new **Web Service** and connect the repo.
3. Render will detect `render.yaml` and pre-fill the service settings.
4. Set the secret env vars (`ANTHROPIC_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD`, `OWNER_EMAIL`) in the Render dashboard — they are marked `sync: false` and must be entered manually.
5. Deploy. First request after a cold start takes ~30 s on the free tier.

Live URL: *(not yet deployed — update this line after deploying to Render)*
