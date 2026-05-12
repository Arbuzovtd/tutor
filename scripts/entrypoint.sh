#!/usr/bin/env bash
# Container entrypoint: run migrations, then launch the bot.
set -euo pipefail

echo "[entrypoint] running alembic upgrade head…"
alembic upgrade head

echo "[entrypoint] launching uvicorn…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
