#!/usr/bin/env bash
# Deploy script for any VPS with Docker + Docker Compose installed.
# Run from the repo root on the VPS, e.g.: bash scripts/deploy.sh
set -euo pipefail

if [[ ! -f .env ]]; then
    echo "❌ .env not found. Copy .env.example to .env and fill in values first." >&2
    exit 1
fi

# Sanity-check required variables before building.
required=("TELEGRAM_BOT_TOKEN" "POSTGRES_PASSWORD")
for var in "${required[@]}"; do
    if ! grep -qE "^${var}=.+" .env; then
        echo "❌ ${var} is empty in .env" >&2
        exit 1
    fi
done

echo "▸ Pulling base images…"
docker compose pull --ignore-pull-failures db

echo "▸ Building bot image…"
docker compose build bot

echo "▸ Starting services…"
docker compose up -d

echo "▸ Waiting for healthcheck…"
for i in {1..30}; do
    if docker compose exec -T bot curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
        echo "✅ Bot is healthy."
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        echo "❌ Bot did not become healthy in 60s. Last 50 log lines:"
        docker compose logs --tail=50 bot
        exit 1
    fi
done

echo
echo "▸ Bot status:"
docker compose ps
echo
echo "▸ Recent logs:"
docker compose logs --tail=20 bot
echo
echo "✅ Deploy complete. Tail logs with: docker compose logs -f bot"
