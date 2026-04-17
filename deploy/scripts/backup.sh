#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="deploy/env/prod.env"
COMPOSE="docker compose --env-file ${ENV_FILE}"
DB_FILE="data/db/db.sqlite3"
MEDIA_DIR="data/media"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[backup] Env file not found: ${ENV_FILE}"
  exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
SQLITE_BACKUP_DIR="backups/sqlite"
POSTGRES_BACKUP_DIR="backups/postgres"
MEDIA_BACKUP_DIR="backups/media"

read_env_var() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- | tr -d '\r' || true
}

wait_for_postgres() {
  local pg_user pg_db
  pg_user="$(read_env_var POSTGRES_USER)"
  pg_db="$(read_env_var POSTGRES_DB)"
  pg_user="${pg_user:-partners_site}"
  pg_db="${pg_db:-partners_site}"

  for _ in {1..60}; do
    if $COMPOSE exec -T db pg_isready -U "${pg_user}" -d "${pg_db}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "[backup] PostgreSQL did not become ready in time"
  exit 1
}

DB_ENGINE="$(read_env_var DB_ENGINE)"
DB_ENGINE="${DB_ENGINE,,}"
DB_ENGINE="${DB_ENGINE:-sqlite}"

if [[ "${DB_ENGINE}" != "sqlite" && "${DB_ENGINE}" != "postgres" ]]; then
  echo "[backup] Unsupported DB_ENGINE=${DB_ENGINE}. Use sqlite or postgres"
  exit 1
fi

mkdir -p "$SQLITE_BACKUP_DIR" "$POSTGRES_BACKUP_DIR" "$MEDIA_BACKUP_DIR"

if [[ -f "$DB_FILE" ]]; then
  cp "$DB_FILE" "${SQLITE_BACKUP_DIR}/db_${TS}.sqlite3"
  echo "[backup] SQLite backup created: ${SQLITE_BACKUP_DIR}/db_${TS}.sqlite3"
else
  echo "[backup] SQLite file not found: $DB_FILE"
fi

if [[ "${DB_ENGINE}" == "postgres" ]]; then
  PG_USER="$(read_env_var POSTGRES_USER)"
  PG_DB="$(read_env_var POSTGRES_DB)"
  PG_USER="${PG_USER:-partners_site}"
  PG_DB="${PG_DB:-partners_site}"

  echo "[backup] Start PostgreSQL service"
  $COMPOSE up -d db
  wait_for_postgres

  POSTGRES_BACKUP_PATH="${POSTGRES_BACKUP_DIR}/db_${TS}.sql.gz"
  if $COMPOSE exec -T db pg_dump -U "${PG_USER}" -d "${PG_DB}" | gzip >"${POSTGRES_BACKUP_PATH}"; then
    echo "[backup] PostgreSQL backup created: ${POSTGRES_BACKUP_PATH}"
  else
    rm -f "${POSTGRES_BACKUP_PATH}"
    echo "[backup] PostgreSQL backup failed"
    exit 1
  fi
fi

if [[ -d "$MEDIA_DIR" ]]; then
  tar -czf "${MEDIA_BACKUP_DIR}/media_${TS}.tar.gz" -C "$MEDIA_DIR" .
  echo "[backup] Media backup created: ${MEDIA_BACKUP_DIR}/media_${TS}.tar.gz"
else
  echo "[backup] Media directory not found: $MEDIA_DIR"
fi

# Retention policy: SQLite 14 days, PostgreSQL 14 days, media 30 days
find "$SQLITE_BACKUP_DIR" -type f -name "*.sqlite3" -mtime +14 -delete
find "$POSTGRES_BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete
find "$MEDIA_BACKUP_DIR" -type f -name "*.tar.gz" -mtime +30 -delete

echo "[backup] Retention cleanup complete"
