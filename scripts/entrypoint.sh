#!/usr/bin/env bash
# Container entrypoint: run migrations, then launch the bot.
# Supports both VPS (fixed port 8000) and Railway (dynamic $PORT).
set -euo pipefail

# Railway / Heroku-style providers give us postgresql:// — SQLAlchemy async
# needs the +asyncpg dialect. Normalize once here so the app code stays naive.
if [[ -n "${DATABASE_URL:-}" ]]; then
    case "$DATABASE_URL" in
        postgres://*)
            export DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgres://}"
            echo "[entrypoint] normalized DATABASE_URL postgres:// → postgresql+asyncpg://"
            ;;
        postgresql://*)
            export DATABASE_URL="postgresql+asyncpg://${DATABASE_URL#postgresql://}"
            echo "[entrypoint] normalized DATABASE_URL postgresql:// → postgresql+asyncpg://"
            ;;
    esac
fi

echo "[entrypoint] running alembic upgrade head…"
alembic upgrade head

PORT="${PORT:-8000}"
echo "[entrypoint] launching uvicorn on 0.0.0.0:${PORT}…"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --proxy-headers
