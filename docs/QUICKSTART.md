# QuickStart — поднять dev окружение

## Первый запуск (с нуля)

```bash
cd /home/ser/my_projects/tutor_automation

# 1. Установить deps (uv делает venv автоматически)
uv sync

# 2. Postgres — должен быть локальный на :5432.
#    Если БД и роль ещё не созданы:
psql -U postgres -h localhost <<'SQL'
CREATE ROLE tutorbot WITH LOGIN PASSWORD 'tutorbot' CREATEDB;
CREATE DATABASE tutorbot OWNER tutorbot;
CREATE DATABASE tutorbot_test OWNER tutorbot;
SQL

# 3. Применить миграции
uv run alembic upgrade head

# 4. .env (если ещё не скопирован)
cp .env.example .env
# отредактировать .env: TELEGRAM_BOT_TOKEN=...

# 5. Запустить тесты
uv run pytest -q

# 6. Поднять бот + FastAPI
uv run uvicorn app.main:app --port 8765 --log-level info
```

## Каждый день

```bash
cd /home/ser/my_projects/tutor_automation
uv run uvicorn app.main:app --port 8765 --log-level info
```

Бот сразу подключается к `@businessbot123bot` и слушает.

## Полезные SQL для просмотра состояния

```bash
# Tutors
psql -U tutorbot -h localhost -d tutorbot -c \
  "SELECT id, telegram_user_id, name, is_registered, is_active, onboarding_status FROM tutors;"

# Business connections
psql -U tutorbot -h localhost -d tutorbot -c \
  "SELECT id, tutor_id, connection_id, is_enabled, can_reply FROM business_connections;"

# Последние 10 сообщений
psql -U tutorbot -h localhost -d tutorbot -c \
  "SELECT id, tutor_id, direction, telegram_message_id, left(text, 60) AS text FROM chat_messages ORDER BY id DESC LIMIT 10;"

# Audit log
psql -U tutorbot -h localhost -d tutorbot -c \
  "SELECT id, tutor_id, action, payload_json, created_at FROM audit_logs ORDER BY id DESC LIMIT 10;"
```

## Смена токена бота (если утёк)

```
@BotFather → /mybots → выбрать бота → API Token → Revoke current token
```

Новый токен положить в `.env`, рестартнуть.

## Создать новую миграцию

```bash
# Изменил модели в app/db/models.py
uv run alembic revision --autogenerate -m "describe what changed"
# отредактировать сгенерированный файл (особенно при добавлении NOT NULL колонки — нужен server_default или backfill)
uv run alembic upgrade head
```

## Запустить только тесты

```bash
uv run pytest -q                    # все
uv run pytest tests/test_tutor_repo.py -v   # один файл
uv run pytest -k "intent" -v        # по подстроке
uv run pytest --cov=app             # с coverage
```

## Линт / форматирование

```bash
uv run ruff check .                 # проверить
uv run ruff check . --fix           # автофиксы
uv run ruff format .                # форматировать
```

## Структура

```
tutor_automation/
├── app/
│   ├── main.py              # FastAPI + bot lifespan
│   ├── config.py            # pydantic-settings из .env
│   ├── db/                  # модели, сессии, репозитории
│   ├── bot/                 # aiogram dispatcher, routers, FSM, middleware
│   ├── calendar/            # Calendar Protocol + InMemory + Google stub
│   ├── ai/                  # intent parser + prompts + prefilter
│   └── security/            # Fernet шифрование
├── alembic/versions/        # миграции
├── tests/                   # 37 тестов, всё через TDD
├── docs/
│   ├── PRD.md               # product spec
│   ├── PLAN.md              # phase plan + статус
│   └── QUICKSTART.md        # этот файл
└── spike/                   # Phase 0 spike — сносится в Phase 5
```
