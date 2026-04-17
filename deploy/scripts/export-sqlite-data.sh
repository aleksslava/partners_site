#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="deploy/env/prod.env"
COMPOSE="docker compose --env-file ${ENV_FILE}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[export] Env file not found: ${ENV_FILE}"
  exit 1
fi

read_env_var() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- | tr -d '\r' || true
}

DB_ENGINE="$(read_env_var DB_ENGINE)"
DB_ENGINE="${DB_ENGINE,,}"
DB_ENGINE="${DB_ENGINE:-sqlite}"

if [[ "${DB_ENGINE}" != "sqlite" ]]; then
  echo "[export] DB_ENGINE must be sqlite for export. Current: ${DB_ENGINE}"
  exit 1
fi

DUMP_PATH="${1:-backups/migration/sqlite_dump_$(date +%Y%m%d_%H%M%S).json}"
mkdir -p "$(dirname "${DUMP_PATH}")"

echo "[export] Ensure web service is running"
$COMPOSE up -d web

echo "[export] Dump SQLite data to ${DUMP_PATH}"
$COMPOSE exec -T web \
  python manage.py dumpdata \
  --natural-foreign \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude admin.logentry \
  > "${DUMP_PATH}"

if [[ ! -s "${DUMP_PATH}" ]]; then
  echo "[export] Dump file is empty: ${DUMP_PATH}"
  exit 1
fi

echo "[export] Done: ${DUMP_PATH}"
