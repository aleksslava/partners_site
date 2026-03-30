#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DB_FILE="data/db/db.sqlite3"
MEDIA_DIR="data/media"

TS="$(date +%Y%m%d_%H%M%S)"
SQLITE_BACKUP_DIR="backups/sqlite"
MEDIA_BACKUP_DIR="backups/media"

mkdir -p "$SQLITE_BACKUP_DIR" "$MEDIA_BACKUP_DIR"

if [[ -f "$DB_FILE" ]]; then
  cp "$DB_FILE" "${SQLITE_BACKUP_DIR}/db_${TS}.sqlite3"
  echo "[backup] SQLite backup created: ${SQLITE_BACKUP_DIR}/db_${TS}.sqlite3"
else
  echo "[backup] SQLite file not found: $DB_FILE"
fi

if [[ -d "$MEDIA_DIR" ]]; then
  tar -czf "${MEDIA_BACKUP_DIR}/media_${TS}.tar.gz" -C "$MEDIA_DIR" .
  echo "[backup] Media backup created: ${MEDIA_BACKUP_DIR}/media_${TS}.tar.gz"
else
  echo "[backup] Media directory not found: $MEDIA_DIR"
fi

# Retention policy: SQLite 7 days, media 30 days
find "$SQLITE_BACKUP_DIR" -type f -name "*.sqlite3" -mtime +7 -delete
find "$MEDIA_BACKUP_DIR" -type f -name "*.tar.gz" -mtime +30 -delete

echo "[backup] Retention cleanup complete"
