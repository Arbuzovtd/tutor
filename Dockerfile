# Multi-stage Dockerfile for TutorBot.
# Stage 1: install Python deps via uv into a virtualenv.
# Stage 2: copy only the venv + app code into a slim runtime image.

FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

WORKDIR /app

# Install dependencies first (cacheable layer).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now install the project itself.
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# ---

FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r tutorbot && useradd -r -g tutorbot -d /app -s /usr/sbin/nologin tutorbot

WORKDIR /app

COPY --from=builder --chown=tutorbot:tutorbot /app/.venv /app/.venv
COPY --chown=tutorbot:tutorbot app/ ./app/
COPY --chown=tutorbot:tutorbot alembic/ ./alembic/
COPY --chown=tutorbot:tutorbot alembic.ini ./
COPY --chown=tutorbot:tutorbot scripts/entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER tutorbot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["./entrypoint.sh"]
