# Dev Landing Backend

Бэкенд на FastAPI для лендинг-презентации разработчика: форма обратной связи с
валидацией, AI-анализ обращения (Google Gemini), email-уведомления, rate limiting,
файловое логирование и метрики.

**Живое демо: https://tema-landing.duckdns.org:88/**

## 1. Как запустить

### Требования
- Python 3.11+

### Установка и запуск
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # затем заполнить значения (все опциональны — сервис работает и без них)
uvicorn app.main:app --reload
```
Открыть http://localhost:8000 (лендинг) и http://localhost:8000/docs (Swagger).

### Переменные окружения
| Переменная | Назначение | По умолчанию |
|-----|---------|---------|
| `GEMINI_API_KEY` | Включает AI-анализ; без неё работает rule-based fallback. Бесплатный ключ: https://aistudio.google.com/apikey | (нет) |
| `AI_MODEL` | ID модели Gemini | `gemini-2.5-flash` |
| `AI_TIMEOUT_SECONDS` | Макс. ожидание ответа Gemini, сек | `12.0` |
| `OWNER_EMAIL` | Получатель письма-уведомления владельцу | `owner@example.com` |
| `SMTP_HOST` | Хост SMTP-сервера (Mailtrap sandbox: `sandbox.smtp.mailtrap.io`) | (нет) |
| `SMTP_PORT` | Порт SMTP — Render блокирует 587, с Mailtrap используйте **2525** | `587` |
| `SMTP_USER` | Имя пользователя SMTP | (нет) |
| `SMTP_PASSWORD` | Пароль SMTP | (нет) |
| `MAIL_FROM` | Адрес отправителя в письмах | `noreply@devlanding.local` |
| `RATE_LIMIT_MAX` | Макс. запросов за окно | `5` |
| `RATE_LIMIT_WINDOW_SECONDS` | Размер скользящего окна, сек | `600` |
| `CORS_ORIGINS` | Разрешённые origins через запятую | `*` |
| `DATA_DIR` | Каталог для лог- и metrics-файлов | `data` |

Все переменные опциональны. Сервис стартует и корректно отвечает с пустым `.env`.

### Тесты
```bash
pytest -v
```
25 тестов, все зелёные. Не требуют живых API-ключей — AI- и email-пути замоканы.

## 2. Стек технологий
- **Backend:** Python 3.11, FastAPI, Uvicorn, Pydantic v2, pydantic-settings
- **AI:** Google Gemini через SDK `google-genai` — структурированный JSON-вывод через `response_schema` (`gemini-2.5-flash`, бесплатный tier)
- **Email:** aiosmtplib + Mailtrap sandbox (SMTP)
- **Валидация:** field-валидаторы Pydantic v2; `email-validator` для `EmailStr`
- **Тесты:** pytest, pytest-asyncio, httpx (async test client)

## 3. Архитектура

Слоистая: **Controllers** (`app/api/`) → **Services** (`app/services/`) → **Handlers** (`app/handlers/`).

```
app/
├── api/          # FastAPI-роутеры — contact.py, metrics.py; health-эндпоинт в main.py
├── services/     # Бизнес-логика — contact_service.py, ai_service.py, email_service.py
├── handlers/     # Инфраструктура — rate_limiter.py, metrics_store.py
├── schemas/      # Pydantic-модели — contact.py (request/response), ai.py (AIAnalysis)
├── core/         # Сквозное — logging.py (настройка + structured logger), errors.py
│                 # (exception handlers), middleware.py (request-logging middleware)
├── static/       # Статический лендинг (index.html, CSS, JS)
├── config.py     # Settings на pydantic-settings с поддержкой .env
├── dependencies.py # Фабрики FastAPI Depends (DI-проводка)
└── main.py       # App-фабрика — CORS, middleware, роутеры, монтирование static
data/             # Создаётся в рантайме: *.log, metrics.json (в .gitignore)
```

**Границы слоёв:**
- Роутеры знают только request/response-схемы и вызывают один метод сервиса.
- Сервисы оркеструют AI, email и метрики; не импортируют FastAPI.
- Handlers — чистые I/O-адаптеры (запись в файл, SMTP, in-memory состояние) без бизнес-логики.

**Почему FastAPI/Python:**
Авто-Swagger из аннотаций типов — нулевая ручная работа по документации. Валидация
Pydantic v2 — одна из строжайших в экосистеме. `async`/`await` хорошо ложится на фоновую
отправку писем. Типизированный подход близок к TS-воркфлоу — переключение контекста дешёвое.

## 4. API

Живые интерактивные доки: http://localhost:8000/docs

### POST /api/contact

Приём формы. Валидирует вход, запускает AI-анализ, планирует отправку писем в фоне,
сразу возвращает анализ.

**Тело запроса (JSON):**
```json
{
  "name": "Alice Founder",
  "email": "alice@example.com",
  "phone": "+1 555 123 4567",
  "comment": "Loved your portfolio — can we discuss a paid project?",
  "honeypot": null
}
```
Ограничения полей: `name` 2–80 символов; `email` валидный по RFC 5322; `phone` 7–20 символов по `^\+?[0-9 ()\-]{7,20}$`; `comment` 5–2000 символов. `honeypot` опционально — любое непустое значение тихо помечает обращение как спам (category `spam`, priority `low`) без возврата ошибки.

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

**422 Unprocessable Entity** — ошибка валидации Pydantic (нет поля, битый email, телефон вне диапазона и т.п.).

**429 Too Many Requests** — превышен rate limit (по умолчанию: 5 запросов за 10 минут на IP).

---

### GET /api/health

Возвращает статус сервиса и флаги конфигурации.

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

Возвращает агрегированную статистику обращений.

**200 OK:**
```json
{
  "total": 12,
  "by_category": { "sales": 7, "support": 2, "spam": 1, "other": 2 },
  "by_sentiment": { "positive": 6, "neutral": 4, "negative": 2 },
  "last_updated": "2026-06-21T10:00:00.000000+00:00"
}
```

---

### GET /

Отдаёт статический лендинг (`app/static/index.html`).

### GET /docs

Авто-Swagger UI (встроен в FastAPI).

## 5. AI-интеграция

Один вызов Gemini на каждое обращение возвращает структурированный JSON, гарантированный
через `response_schema` (SDK ограничивает модель Pydantic-схемой, поэтому ответ — всегда
валидный JSON):

```json
{
  "sentiment": "positive" | "neutral" | "negative",
  "category":  "sales"    | "support" | "spam"    | "other",
  "priority":  "low"      | "normal"  | "high",
  "suggested_reply": "<строка, ≤80 слов, на языке исходного сообщения>"
}
```

**Системный промпт** (дословно из `app/services/ai_service.py`):
```
You are an assistant that triages inbound messages from a developer's
landing page contact form. Analyze the user's message and return the
sentiment, the request category, a priority, and a short, polite draft
reply in the same language as the message. Do not invent facts about the
site owner. Keep the draft reply under 80 words.
```

**Graceful fallback** — срабатывает, когда:
- `GEMINI_API_KEY` не задан
- Gemini вернул ошибку или истёк таймаут (12 с по умолчанию)

Fallback — это keyword-движок (`rule_based_fallback` в `ai_service.py`). Он матчит ключевые
слова для priority (`urgent`, `asap`, `срочно`…), category (`project`, `hire`, `collaborat`…)
и sentiment (`bad`, `terrible`, `ужас`…). Ответ всегда HTTP 200; в объекте анализа
`ai_available` равно `false`, когда использован fallback.

## 6. Что сделано с помощью AI

> **Build-time vs runtime:** проект *написан* с помощью Claude (Anthropic) как инструмента разработки, а *рантайм*-фича (AI-анализ обращения) вызывает **Google Gemini**. Два разных применения AI — одно пишет код, другое работает внутри продукта.

Вся реализация — все исходники и тесты — сгенерирована субагентами Claude (Anthropic) по
детальному плану из 13 задач (spec-driven TDD):

- **Сгенерировано AI:** пакет `app/` (config, schemas, services, handlers, api-роутеры, middleware, core-утилиты, статический лендинг), `tests/` (25 pytest-тестов: happy path, валидация, rate limiting, AI-fallback, email no-op, honeypot, метрики, логирование), `requirements.txt`, `.env.example`, `render.yaml`, `postman_collection.json`.
- **Использованные промпты:** у каждой задачи был бриф в `.git/sdd/task-N-brief.md` с точными путями файлов, интерфейсами и ожидаемым покрытием тестами. Субагенты шли по TDD: написать тесты → довести до зелёного → self-review против спеки.
- **Ручные правки:** интеграционные моменты, требующие кросс-задачного контекста: жизненный цикл логгера (инициализация до срабатывания middleware), порядок middleware (CORS перед RequestLogging), проводка DI (`app/dependencies.py`), и смена рантайм-провайдера AI на Gemini (structured output через `response_schema`, модель-схема без дефолтов из-за googleapis/python-genai#699).
- **Контроль:** после каждой задачи все 25 тестов проверялись на зелёный; финальная интеграция сверена с полным чек-листом спеки.

## 7. Хранение данных

Все рантайм-данные пишутся в `data/` (создаётся автоматически при первом запуске; в `.gitignore`).

| Файл | Формат | Содержимое |
|------|--------|---------|
| `data/requests.log` | JSON Lines | Одна запись на HTTP-запрос: `request_id`, `method`, `path`, `ip`, `status`, `latency_ms` (без PII и тела сообщения) |
| `data/app.log` | JSON Lines | События приложения: предупреждения AI-fallback, результаты отправки писем, ошибки |
| `data/metrics.json` | JSON-объект | Агрегированные счётчики (total, by_category, by_sentiment, last_updated); запись атомарная через temp-файл + rename |

**Rate limiting** — in-memory счётчик со скользящим окном по IP клиента. Состояние теряется
при рестарте. Для продакшена заменяется на Redis-бэкенд (напр. `redis-py` + `aioredis`).

## Деплой

**Живое демо: https://tema-landing.duckdns.org:88/** — лендинг, плюс `GET /api/health`, `GET /api/metrics` и Swagger на `/docs`.

Развёрнуто на личном Ubuntu VPS через Docker (`Dockerfile` + `compose.vps.yml`), за общим
reverse-proxy Caddy, который терминирует TLS (Let's Encrypt). Нестандартный порт `:88` — потому
что `443` на хосте занят другим сервисом; Caddy мапит хостовый `:88` на свой внутренний `:443`.
AI-анализ работает вживую на Google Gemini.

> **Email в живом демо:** SMTP-слой реализован и покрыт юнит-тестами, но хостинговый инстанс
> работает **без SMTP-кредов**, поэтому письма-уведомления пишутся в `data/app.log`, а не
> отправляются. Чтобы включить реальную доставку — задать `SMTP_HOST` / `SMTP_PORT` /
> `SMTP_USER` / `SMTP_PASSWORD` (подойдёт Mailtrap inbox или Gmail App Password).

Запустить у себя — по [инструкции выше](#1-как-запустить), либо через контейнер:

```bash
docker compose up -d --build   # отдаёт на http://localhost:8000
```
