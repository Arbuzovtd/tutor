#!/usr/bin/env bash
# Postgres backup. Writes a timestamped .sql.gz to ./backups/.
# Run from the VPS, ideally from cron: 0 3 * * * cd /opt/tutorbot && bash scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

# Read POSTGRES_USER / POSTGRES_DB from .env (default values match docker-compose.yml).
PG_USER=$(grep -E "^POSTGRES_USER=" .env 2>/dev/null | cut -d= -f2 || echo "tutorbot")
PG_DB=$(grep -E "^POSTGRES_DB=" .env 2>/dev/null | cut -d= -f2 || echo "tutorbot")
PG_USER=${PG_USER:-tutorbot}
PG_DB=${PG_DB:-tutorbot}

TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$BACKUP_DIR/${PG_DB}_${TS}.sql.gz"

echo "▸ Dumping ${PG_DB} as ${PG_USER} → ${OUT}"
docker compose exec -T db pg_dump -U "$PG_USER" "$PG_DB" | gzip > "$OUT"

# Keep last 14 days.
find "$BACKUP_DIR" -name "${PG_DB}_*.sql.gz" -mtime +14 -delete

echo "✅ Backup done: $(du -h "$OUT" | cut -f1)"
