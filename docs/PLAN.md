# TutorBot — Implementation Plan & Status

**Снимок состояния:** 2026-05-10 (поздний вечер)

---

## Краткое резюме

4 коммита, 37 tests green, ~1500 строк кода. Фундамент стоит, бот живёт, AI-парсер тестируется на моках.

```
9198cc4  feat(ai): intent parser with regex pre-filter and JSON-mode GPT-4o adapter
a4c4202  feat(calendar): introduce backend Protocol, in-memory impl, Fernet at-rest crypto
c9fa1c1  feat(bot): wire aiogram into FastAPI with DB-gated registration
4371a48  feat: validate Telegram Business Mode and lay async DB foundation
```

---

## Phase Status Table

| # | Name | Status | Model used | Blocker |
|---|---|---|---|---|
| 0 | Spike Telegram Business Mode | ✅ Done | Sonnet | — |
| 1 | Foundation (DB + skeleton + repos) | ✅ Done | Haiku | — |
| 2 | Bot core + FSM Onboarding + Auth gate | ✅ Done | Sonnet | live test через `/start` ещё не запускался |
| 3 | Calendar Protocol + Fernet | 🟡 Partial | Sonnet | OAuth flow ⏸ — нужны `GOOGLE_CLIENT_ID/SECRET` |
| 4 | AI Intent Parser | 🟡 Partial | Sonnet | Real-API integration ⏸ — нужен `OPENAI_API_KEY` |
| 5 | Reschedule Decision Engine | ⏸ Not started | Sonnet | — все зависимости готовы, можно стартовать |
| 6 | Personal Time `/block` | ⏸ Not started | Sonnet | depends on 5 |
| 7 | Morning Summary 9:00 | ⏸ Not started | Haiku | depends on 5 |
| 8 | Tutor-in-the-loop review | ⏸ Not started | Sonnet | depends on 5 |
| 10 | Deploy + Hardening (Railway) | ⏸ Not started | Sonnet | depends on 5–8 |

---

## Что готово в коде

### Phase 0 — Spike (`spike/`)
- `spike/bot.py` — минимальный handler `business_connection` + `business_message`
- `spike/README.md` — пошаговая инструкция по @BotFather + Settings
- Подтверждено живыми пакетами: aiogram 3.28 принимает business updates и шлёт ответы через `business_connection_id`
- Можно удалить после старта Phase 5 (заменён `app/bot/`)

### Phase 1 — Foundation (`app/db/`, `alembic/`, `tests/`)
- 8 моделей (`Tutor`, `BusinessConnection`, `Student`, `Lesson`, `ChatMessage`, `AuditLog`, `OAuthToken`, `PersonalBlock`) — все multi-tenant с `tutor_id` FK CASCADE
- `app/db/repositories/{tutor.py, business_connection.py}` — repository pattern
- 7 TDD-тестов на репозитории
- Alembic async (env.py с pydantic-settings), 2 миграции
- FastAPI `/healthz`, `/readyz`
- Local Postgres 16 на `:5432`, role `tutorbot:tutorbot`, dbs `tutorbot` + `tutorbot_test`

### Phase 2 — Bot core (`app/bot/`)
- `dispatcher.py` — Bot factory + Dispatcher с FSM MemoryStorage и DI middleware
- `middlewares/db.py` — `DbSessionMiddleware` инжектит `AsyncSession` в каждый handler
- `routers/business.py` — `business_connection` (upsert), `business_message` (auth-gated)
- `routers/tutor_cmds.py` — `/start`, `/help`, `/cancel` (только direct chat, не business)
- `routers/onboarding.py` — FSM 4 шага (subjects → grades → hours → price → complete)
- `states.py` — `Onboarding` StatesGroup
- `app/main.py` — bot polling в lifespan FastAPI (1 процесс на dev)
- **Auth gate:** `Tutor.is_registered` (default False) → flips True на финале FSM. business_message обрабатывается только если `is_registered AND is_active`. Иначе `direction='inbound_ignored'` в audit, бот молчит.
- Migration `227e1c4037d6` с backfill для tutors с `onboarding_status='info_collected'`

### Phase 3 partial — Calendar (`app/calendar/`, `app/security/`)
- `base.py` — `CalendarBackend` Protocol + frozen `CalendarEvent` dataclass
- `inmemory.py` — `InMemoryCalendar` (для unit-тестов engine в Phase 5)
- `google.py` — stub класс, методы поднимают `NotImplementedError`
- `app/security/fernet.py` — `FernetCipher` для шифрования OAuth refresh tokens
- 6 тестов на InMemoryCalendar, 3 на Fernet

### Phase 4 partial — AI (`app/ai/`)
- `types.py` — `IntentKind` (StrEnum: reschedule/cancel/question/unknown), `IntentResult` (pydantic)
- `prompts.py` — `INTENT_SYSTEM_PROMPT` на русском с few-shot для относительных дат
- `prefilter.py` — regex-based `is_scheduling_message()` (стемы: "перенес", "отмен", дни недели, время)
- `intent.py` — `IntentParser` с `CompleterProtocol` DI; defensive fallback на UNKNOWN при любых ошибках
- `client.py` — `OpenAICompleter` (production wrapper над `AsyncOpenAI` JSON-mode)
- 9 параметризованных тестов на prefilter, 6 сценариев на парсер

---

## Architecture (high-level)

```
┌────────────────────────────────────────────────────────────┐
│                Telegram (Business Mode)                    │
│  Tutor's Account ──┬── Student chats (via Chat Automation) │
└────────────────────┼───────────────────────────────────────┘
                     │ business_message updates
                     ▼
        ┌────────────────────────┐
        │  aiogram 3.28 Bot      │ ◄── direct chat with tutor (FSM)
        │  Dispatcher + Routers  │
        │  + DbSessionMiddleware │
        └─────────┬──────────────┘
                  │
                  ▼
        ┌────────────────────────┐      ┌──────────────────┐
        │  Decision Engine       │ ◄──► │ OpenAICompleter  │
        │  (Phase 5)             │      │ (JSON-mode GPT)  │
        └────┬──────────┬────────┘      └──────────────────┘
             │          │
             ▼          ▼
   ┌────────────┐  ┌─────────────┐
   │ Calendar   │  │ PostgreSQL  │
   │ Backend    │  │ (multi-     │
   │ (Google /  │  │  tenant)    │
   │ InMemory)  │  └─────────────┘
   └────────────┘
             ▲
             │
    ┌────────────────┐
    │ FastAPI        │ ◄── /healthz /readyz
    │ /oauth/google  │     (Phase 3 finish)
    └────────────────┘
```

---

## Что висит на пользователе

| # | Что | Зачем | Когда нужно |
|---|---|---|---|
| 1 | `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` | Google Calendar OAuth | Phase 3 finish |
| 2 | `OPENAI_API_KEY` | Реальные GPT вызовы | Phase 4 live test или Phase 5 demo |
| 3 | `business_connection` восстановление | После dev DB switch коннект потерян | До live теста business_message |
| 4 | Live test `/start` к `@businessbot123bot` | Подтвердить onboarding FSM работает | Когда удобно |
| 5 | Решить — invite-коды или открытая регистрация | Сейчас auth gate = открытая регистрация через FSM | Phase 8 / перед публичным запуском |

### Как восстановить business_connection

**Вариант A (один клик):** Settings → Telegram Business → Chatbots → найти `@businessbot123bot` → переключить любую галку (например "Manage Messages") → Save. Это вызовет свежий `business_connection` update, наш handler сохранит запись в БД.

**Вариант B (admin script):** написать `app/scripts/fetch_connection.py` который дёрнет `bot.get_business_connection(connection_id)` — мы знаем `connection_id` из логов спайка: `cmXe57RRAUgCGwAAo5heo8MDGGc`.

### Как создать Google OAuth credentials

1. https://console.cloud.google.com → создать проект "TutorBot"
2. APIs & Services → Library → "Google Calendar API" → Enable
3. APIs & Services → OAuth consent screen → External → fill name/email/scopes
4. APIs & Services → Credentials → Create Credentials → OAuth client ID
5. Application type: Web application
6. Authorized redirect URIs: `http://localhost:8765/oauth/google/callback` (для dev) и потом `https://<railway-domain>/oauth/google/callback` для prod
7. Скопировать `client_id` + `client_secret` → положить в `.env`

---

## Что делать в следующей сессии

### Опция A — Phase 5 (рекомендую)

**Reschedule Decision Engine** — главное сердце. Все зависимости готовы:
- IntentParser ✓ (можно через `OpenAICompleter` с реальным API ИЛИ через mock-completer для dev)
- InMemoryCalendar ✓ (или GoogleCalendarBackend когда OAuth готов)
- TutorRepository, BusinessConnectionRepository ✓
- Нужно дописать: `ChatMessageRepository`, `LessonRepository`, `AuditLogRepository`

**Что делает Phase 5:**
- `app/services/reschedule.py:handle_business_message()` — entrypoint от `business.py`
- Проверка идемпотентности (по `business_connection_id + telegram_message_id`)
- Identification ученика (по `from_user.id`)
- Handoff detection (если репетитор сам ответил недавно — молчим 60 мин)
- `intent = parser.parse(text, current_dt)` → branching
- Reschedule path: проверить календарь → принять / предложить альтернативы / уточнить
- Cancel path: подтвердить → удалить event
- Low-confidence path → сохранить в "tutor review queue", прислать draft с inline keyboards
- Postgres advisory locks per `tutor_id` для anti-race
- Все решения → `AuditLog`

**Сроки:** ~3 рабочих дня по плану. В одну сессию реалистично сделать всю логику + golden-path тесты.

### Опция B — Phase 3 finish (если Google creds готовы)

- `OAuthTokenRepository` с TDD
- `GoogleCalendarBackend` живая реализация с `google-api-python-client`
- `app/web/routes.py`: `GET /oauth/google/start?tutor_id=` + `GET /oauth/google/callback`
- HTML success-страница

### Опция C — Polish + live test

- Live test Phase 2 onboarding
- Восстановить `business_connection`
- Удалить `spike/` (после успешного live теста)
- Добавить `app/db/repositories/{student,chat_message,lesson,audit_log,oauth_token,personal_block}.py` со скелетом

---

## Открытые вопросы / решения которые нужно принять

1. **Subscription gate** — сейчас любой может пройти FSM и зарегаться. Когда пойдёшь к платным юзерам — нужен gate (Stripe/YooMoney или invite-коды).
2. **Resilient handoff detection** — как точно определять что репетитор сам ответил в чате (а не бот). Нужно различать `outbound_bot` vs `outbound_tutor` в `chat_messages.direction`.
3. **GPT prompt iteration** — текущий промпт минимальный. Нужны живые примеры от тестового репетитора чтобы тюнить few-shot.
4. **Webhook vs polling** — сейчас polling. Для prod webhook надёжнее, но требует HTTPS endpoint и deploy. Phase 10.
