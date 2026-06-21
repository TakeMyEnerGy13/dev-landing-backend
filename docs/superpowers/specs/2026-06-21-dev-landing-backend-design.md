# Dev Landing Backend — Design Doc

**Дата:** 2026-06-21
**Дедлайн:** 2026-06-22
**Контекст:** Тестовое задание (backend-ориентированное). Бэкенд-сервис для лендинг-презентации разработчика с REST API, email-уведомлениями и AI-интеграцией.

---

## 1. Цель и объём

Бэкенд-сервис, реализующий **полный цикл обработки обращения с формы обратной связи**:

```
запрос → валидация → бизнес-логика → AI-анализ → отправка email → ответ
```

Плюс лёгкий фронтенд-лендинг (one-page) как «большой плюс» по критериям оценки.

**В объёме:**
- REST API `POST /api/contact` с валидацией и санитизацией
- Email-уведомления: письмо владельцу + копия пользователю
- AI-анализ обращения (один вызов Claude → структурированный вердикт) с graceful fallback
- Rate limiting (in-memory, thread-safe)
- Структурное логирование запросов в файл
- Эндпоинты `GET /api/health`, `GET /api/metrics`
- Глобальная обработка ошибок, CORS, авто-Swagger
- Лендинг (static) с формой, бьющей в API
- README (7 разделов), Postman-коллекция, деплой на Render

**Вне объёма (сознательно, YAGNI на 1 день):** база данных, Redis, очереди, аутентификация, аутентификация админки метрик.

---

## 2. Стек и обоснование

| Технология | Зачем |
|---|---|
| **Python 3.11 + FastAPI** | Ближе всего к TS-DX автора (type hints как типы). Авто-Swagger из коробки — закрывает обязательное требование без ручной работы. Async-native для AI+email I/O. |
| **Pydantic v2** | Декларативная валидация/санитизация — закрывает критерий безопасности. |
| **Anthropic SDK** | AI-интеграция через tool use (structured output) — гарантированно валидный JSON. |
| **Mailtrap sandbox + aiosmtplib** | Реальная SMTP-отправка без риска спама; письма видны в Mailtrap inbox (скриншот в README). |
| **In-memory rate limiter + asyncio.Lock** | Корректнее файлового (нет race conditions/PermissionError). На Render free tier один воркер. В README — обоснование «в проде Redis». |
| **Файловое хранилище (JSON + log)** | Метрики и логи — без БД, как разрешает задание. |
| **Render** | Бесплатный деплой из GitHub, рабочая ссылка на API. |

---

## 3. Архитектура (слоистая: Controllers → Services → Handlers)

```
app/
├── main.py                 # FastAPI app, CORS, регистрация роутов и error handlers
├── config.py               # Settings (pydantic-settings, читает .env)
├── api/                    # Controllers — только HTTP, без бизнес-логики
│   ├── contact.py          # POST /api/contact
│   ├── health.py           # GET  /api/health
│   └── metrics.py          # GET  /api/metrics
├── schemas/                # Pydantic-модели (валидация + OpenAPI examples)
│   ├── contact.py          # ContactRequest / ContactResponse
│   └── ai.py               # AIAnalysis
├── services/               # Бизнес-логика (оркестрация)
│   ├── contact_service.py  # полный цикл обработки обращения
│   ├── ai_service.py       # вызов Claude + rule-based fallback
│   └── email_service.py    # 2 письма (owner + копия юзеру)
├── handlers/               # Repositories — доступ к хранилищу
│   ├── metrics_store.py    # data/metrics.json (atomic write)
│   └── rate_limiter.py     # in-memory счётчик по IP + asyncio.Lock
├── core/
│   ├── logging.py          # настройка JSON-логгера в файл
│   ├── errors.py           # кастомные исключения + глобальный handler
│   └── middleware.py       # request-logging middleware
└── static/                 # лендинг: index.html, style.css, app.js

data/                       # gitignored, создаётся на старте
├── requests.log            # лог всех запросов (JSON-строки)
├── app.log                 # ошибки и AI/email-события
└── metrics.json            # статистика обращений
tests/                      # pytest
.env.example
README.md
postman_collection.json
render.yaml
requirements.txt
```

**Принцип слоёв:** контроллер не знает про SMTP/Claude/файлы; сервис не знает про HTTP; handler не знает про бизнес-правила. Каждый слой тестируется изолированно.

---

## 4. Поток запроса `POST /api/contact`

```
request-logging middleware           → пишет ts/method/path/ip/status/latency/request_id в requests.log
  → RateLimiter.check(ip)             → 429 + Retry-After при превышении (5 req / 10 min)
  → Pydantic ContactRequest           → 422 при невалидных данных
  → honeypot заполнен?                → да: фейковый 200, без AI и email (анти-спам)
  → ContactService.handle():
       ├─ AIService.analyze(comment)  → Claude tool-use → {sentiment, category, priority, suggested_reply}
       │                                 fallback при ошибке/нет ключа → rule-based классификатор
       ├─ BackgroundTasks: EmailService.send_owner(data + ai)
       ├─ BackgroundTasks: EmailService.send_user_copy(data)
       └─ MetricsStore.increment(category, sentiment)
  → 200 { success, message, analysis }  (письма досылаются в фоне)
```

**Ключевое решение — email в background:** AI-анализ остаётся в запросе (его результат идёт в ответ), но отправка писем вынесена в FastAPI `BackgroundTasks` — ответ возвращается мгновенно, не блокируясь на SMTP (1–3 сек). Сбой доставки логируется в `app.log`, а не роняет запрос. Полный цикл (включая отправку) показан в README-диаграмме; в коде отправка вынесена в фон как продакшен-паттерн.

---

## 5. Эндпоинты

| Метод | Путь | Назначение | Статусы |
|---|---|---|---|
| `POST` | `/api/contact` | Приём обращения, AI-анализ, email | 200 / 422 / 429 |
| `GET` | `/api/health` | Статус сервиса | 200 |
| `GET` | `/api/metrics` | Статистика обращений | 200 |
| `GET` | `/docs` | Авто-Swagger (кастомизированный) | 200 |
| `GET` | `/` | Лендинг (static) | 200 |

**`/health`** → `{status, uptime, ai_available, email_configured}`
**`/metrics`** → `{total, by_category, by_sentiment, last_24h}`

---

## 6. Валидация и санитизация (Pydantic)

| Поле | Правила |
|---|---|
| `name` | str, 2–80 символов, trim |
| `email` | `EmailStr` |
| `phone` | regex (E.164-ish: `+`, цифры, пробелы, дефисы), 7–20 символов |
| `comment` | str, 5–2000 символов, trim |
| `honeypot` | Optional[str], скрытое поле; непусто → спам |

Санитизация: `strip()` + жёсткие лимиты длины (защита от инъекций в тело письма). Все поля экранируются при вставке в HTML-письмо.

---

## 7. Обработка ошибок

- **Глобальный exception handler** → единый JSON `{error, detail, request_id}` с корректным HTTP-статусом.
- **Кастомные исключения:** `AIServiceError`, `EmailDeliveryError`, `RateLimitExceeded`.
- **AI-сбой не валит запрос** — отрабатывает fallback, ответ 200.
- **Email-сбой не валит запрос** — отправка в background, ошибка в `app.log`.
- `422` (валидация) и `429` (rate limit) — стандартные, с понятным телом.

---

## 8. AI-интеграция

**Один вызов Claude** через **tool use / structured output** — модель обязана вернуть валидную структуру:

```json
{
  "sentiment": "positive | neutral | negative",
  "category": "sales | support | spam | other",
  "priority": "low | normal | high",
  "suggested_reply": "черновик ответа на обращение"
}
```

Результат кладётся в письмо владельцу (готовый вердикт + черновик ответа) и в метрики.

**Системный промпт (черновик):**
> Ты — ассистент входящих обращений с лендинга разработчика. Проанализируй сообщение пользователя и верни строго структурированный результат: тональность, категорию запроса, приоритет и вежливый черновик ответа на русском. Не выдумывай фактов о владельце.

**Graceful fallback (rule-based, не заглушка):**
При ошибке Claude / таймауте / отсутствии `ANTHROPIC_API_KEY` — локальный keyword-классификатор:
- стоп-слова `срочно/urgent/asap` → `priority: high`
- `сотрудничество/вакансия/проект/hire` → `category: sales`
- негативные маркеры → `sentiment: negative`
- иначе → нейтральные дефолты

Ответ остаётся `200`, флаг `ai_available: false` в `/health`. Fallback приносит пользу даже без сети.

---

## 9. Хранение данных

| Что | Где | Как |
|---|---|---|
| Лог запросов | `data/requests.log` | JSON-строка на запрос (грепается/парсится) |
| Ошибки/события | `data/app.log` | JSON-строки |
| Статистика | `data/metrics.json` | atomic write (temp + rename) |
| Rate limit | in-memory dict | `{ip: [timestamps]}` + asyncio.Lock, сбрасывается при рестарте |

---

## 10. Rate limiting

In-memory скользящее окно: **5 запросов / 10 минут** на IP (порог из `.env`). При превышении — `429` + заголовок `Retry-After`. Thread-safe через `asyncio.Lock`. Обоснование выбора (vs файловый/Redis) — в README.

---

## 11. Логирование

- **requests.log** — каждый запрос: `ts, method, path, ip, status, latency_ms, request_id`
- **app.log** — ошибки, AI-fallback события, email success/failure
- Формат — JSON-строки. `request_id` (uuid) связывает запись запроса с ошибками.

---

## 12. Тесты (pytest)

- Валидация: happy path + невалидные кейсы (короткое имя, битый email/phone, пустой comment) → 422
- Rate limit: 6-й запрос за окно → 429
- AI fallback: мок падения Claude → 200, `ai_available=false`, rule-based вердикт
- Honeypot: заполненное поле → 200 без отправки
- Email: мок транспорта (реально не шлём в тестах)
- `/health`, `/metrics` — структура ответа
- **Критичный кейс:** запуск с пустым `.env` (нет ключа) не падает на импорте SDK

---

## 13. Поставка

- **README** (7 разделов из задания): запуск, стек, архитектура, API, AI-интеграция, что сделано с AI, хранение данных.
- **Postman-коллекция** — примеры всех эндпоинтов.
- **.env.example** — все переменные с комментариями.
- **render.yaml** — деплой одним push.
- Рабочая ссылка на Render + локальная инструкция.

---

## 14. Риски и проверки перед сдачей

1. **SMTP-порты на Render** — проверить, что Mailtrap пробивается из облака (Render может резать 25; использовать 587/2525), не только локально.
2. **Пустой `.env`** — fallback должен работать без `ANTHROPIC_API_KEY`, без падения на импорте.
3. **Cold start Render free tier** (~30 сек первый запрос) — упомянуть в README, чтобы ревьюер не счёл за баг.
4. **Кастомный OpenAPI** — не оставлять дефолтный Swagger: `openapi_examples`, описания 429/422, теги с пояснением AI-логики.

---

## 15. Решения, принятые при проектировании

- **Стек Python/FastAPI** (не PHP) — близость к TS-опыту автора, авто-Swagger, скорость за день.
- **Email в background** (не синхронно) — продакшен-паттерн, не блокирует ответ; цикл показан в README.
- **In-memory rate limiter** (не файловый) — корректность под конкуренцией; задание допускает оба.
- **Rule-based AI fallback** (не заглушка) — fallback реально полезен.
- **Honeypot** — дешёвая анти-спам защита, сигнал понимания реальных лендингов.
- **Без БД** — задание разрешает файлы; БД не добавляет ценности за день и размывает фокус.
