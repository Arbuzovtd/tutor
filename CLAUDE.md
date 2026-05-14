# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**TutorBot** — SaaS for solo tutors (15–25 students) in CIS. A Telegram bot that connects via **Telegram Business Mode** (`businessConnectionId`) and replies to students on the tutor's behalf — accepts reschedules, checks calendar, blocks personal time. Tutor never installs anything beyond linking the bot in `Settings → My Account → Chat Automation`.

**Status:** MVP closed (148 tests green, ~2000 LOC app). Google Calendar OAuth is deferred — `InMemoryCalendar` is used. Deploy target is **Railway** (current `docker-compose.yml` / `Dockerfile` targets generic VPS; not yet on Railway).

Reference docs in this repo:
- `docs/PRD.md` — product spec, pricing, scope decisions
- `docs/PLAN.md` — phase-by-phase implementation status
- `docs/QUICKSTART.md` — dev setup
- `docs/DEPLOY.md` — VPS deploy (Cloud.ru / Oracle / Hetzner) via Docker Compose

## Commands

Package manager is **uv** (Python 3.12). Local DB is **host-native Postgres on `localhost:5432`** — do NOT use Docker for dev (see Memory: `feedback_no_docker_for_dev`).

```bash
# install deps (auto-creates .venv)
uv sync

# run app (FastAPI + bot polling in one process)
uv run uvicorn app.main:app --port 8765 --log-level info

# migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"

# tests
uv run pytest -q                          # all
uv run pytest tests/test_intent_parser.py # one file
uv run pytest -k "intent" -v              # by name substring
uv run pytest --cov=app                   # with coverage

# lint / format
uv run ruff check . --fix
uv run ruff format .
```

DB bootstrap (first time only):

```bash
psql -U postgres -h localhost <<'SQL'
CREATE ROLE tutorbot WITH LOGIN PASSWORD 'tutorbot' CREATEDB;
CREATE DATABASE tutorbot OWNER tutorbot;
CREATE DATABASE tutorbot_test OWNER tutorbot;
SQL
```

## Architecture

**Single-process FastAPI app.** `app/main.py` defines a `lifespan` that:
1. Builds an aiogram `Bot` + `Dispatcher` via `app.bot.dispatcher.make_dispatcher`.
2. Starts a long-polling task with explicit `ALLOWED_UPDATES` (must include `business_connection`, `business_message`, `edited_business_message`, `deleted_business_messages` — Telegram does not send these by default).
3. Starts APScheduler (`app.services.scheduler.make_scheduler`) for the 9:00-local morning summary, cron-checked every minute.
4. On shutdown: flushes the `InboundDebouncer`, stops polling, disposes engine.

`/healthz` (no DB) and `/readyz` (touches DB) are FastAPI routes for liveness/readiness.

### Inbound message pipeline

```
student → business_message → InboundDebouncer (4s quiet / 20s cap)
       → process_message_burst (engine)
       → IntentParser (Polza/OpenAI, JSON mode, prompt-injection envelope)
       → handle_business_message:
            ├─ ack to student in business chat
            └─ ping tutor in DM with inline keyboard [✅ / ❌]
                  → callback → review.py → reply to student via business connection
                  → audit_log entry
```

Key invariants:
- **Multi-tenant root is `Tutor`.** Every business table FK-cascades on `tutor_id`; all queries fan out from there.
- **Idempotency on inbound:** `chat_messages` has `UNIQUE(business_connection_id, telegram_message_id)`.
- **Tutor handoff:** if the tutor replies in the chat themselves, the bot stays silent for 60 min.
- **Rate limit:** 30 events/min per user, 10/min per student per business connection (in-memory, pre-DB middleware).
- **LLM cost cap:** `OPENAI_MAX_TOKENS` (default 300).
- **Prompt injection:** student text wrapped in `<student_message>...</student_message>` and sanitized in `app/ai/intent.py`.
- **Cross-tenant auth check** on every callback in `review.py`.

### Layout

```
app/
├── main.py              FastAPI + bot lifespan
├── config.py            pydantic-settings (loads .env)
├── db/
│   ├── models.py        8 SQLAlchemy 2.x async models (Tutor, BusinessConnection,
│   │                     Student, Lesson, ChatMessage, AuditLog, OAuthToken, PersonalBlock)
│   ├── repositories/    one repo per aggregate
│   └── session.py       async engine + AsyncSessionLocal
├── bot/
│   ├── dispatcher.py    Bot/Dispatcher factory, ALLOWED_UPDATES, middleware wiring
│   ├── deps.py          IntentParser DI
│   ├── middlewares/     rate_limit (outer) + db session (outer)
│   ├── routers/         business, onboarding (FSM), review (callbacks), tutor_cmds
│   └── states.py        aiogram FSM states
├── ai/
│   ├── client.py        OpenAI SDK (honors OPENAI_BASE_URL for Polza)
│   ├── intent.py        IntentParser with JSON mode + retries
│   ├── prefilter.py     regex prefilter (skips ~70% of LLM calls)
│   └── prompts.py       system prompt + envelope
├── calendar/
│   ├── base.py          Calendar Protocol
│   ├── inmemory.py      used in tests + MVP
│   └── google.py        stub (OAuth deferred post-MVP)
├── services/
│   ├── debouncer.py     InboundDebouncer (4s/20s burst-typing coalesce)
│   ├── reschedule.py    handle_business_message — 8-branch decision engine
│   ├── block_parser.py  parses "/block today 14-15 обед"
│   ├── morning_summary.py
│   └── scheduler.py     APScheduler cron
└── security/
    └── fernet.py        for encrypting OAuth tokens at rest
```

Routers are included in this order (matters for command precedence): `tutor_cmds → onboarding → review → business`.

### Tutor-facing commands

`/start` (FSM onboarding) · `/today` · `/lessons` · `/students` · `/summary` · `/block <when> <range> <label>` · `/blocks` · `/unblock <id>` · `/help` · `/cancel`.

`/start` FSM sets `Tutor.is_registered = True` on completion — that flag is the auth gate (no `.env` whitelist).

## Configuration

All settings come from `.env` via `pydantic-settings` (`app/config.py`). Required: `TELEGRAM_BOT_TOKEN`. Optional: `OPENAI_API_KEY` (bot stays silent on student messages if unset), `OPENAI_BASE_URL` (set to `https://api.polza.ai/v1` for Polza — must be `https://`), `OPENAI_MODEL` (default `gpt-4o-mini`), `OPENAI_MAX_TOKENS` (default 300), `DATABASE_URL`, `SENTRY_DSN`, `FERNET_KEY` (needed once Google OAuth is enabled).

DB URL must be the **asyncpg** dialect: `postgresql+asyncpg://...` — Alembic and SQLAlchemy share this URL via `get_settings()`.

## Deployment

**Current state:** Docker Compose stack (`bot` + `db`) tuned for 1 GB VMs. `scripts/deploy.sh` builds image, brings stack up, waits for `/healthz`. `scripts/backup.sh` does nightly `pg_dump` to `./backups/` with 14-day retention. The container `entrypoint.sh` runs `alembic upgrade head` then `uvicorn` on port 8000.

**Target: Railway.** Not yet wired. When migrating: replace `docker-compose.yml`'s `db` service with Railway's managed Postgres add-on (set `DATABASE_URL`), have the bot service read `$PORT` for uvicorn, and keep the same `entrypoint.sh` (migrations on every boot). Long-polling is outbound-only so no public ingress is required for Telegram, but Railway needs the health port exposed.

## Conventions

- **Tests first.** TDD across all phases — coverage stays high (`pytest --cov=app`).
- **Async everywhere:** SQLAlchemy 2 async, asyncpg, aiogram 3.x. No sync DB calls anywhere.
- **Repositories own queries**; routers/services consume them — do not call `session.execute(select(...))` from a router.
- **Don't add new top-level dirs without updating Dockerfile + `.dockerignore`** (only `app/`, `alembic/`, `alembic.ini`, `scripts/entrypoint.sh` are copied into the runtime image).
- **`spike/`** is leftover Phase 0 throwaway code — do not import from it.
