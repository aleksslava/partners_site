#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="deploy/env/prod.env"
COMPOSE="docker compose --env-file ${ENV_FILE}"
APPS=(admin auth contenttypes sessions shop taggit users orders integrations)

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[import] Env file not found: ${ENV_FILE}"
  exit 1
fi

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

  echo "[import] Waiting for PostgreSQL (db=${pg_db}, user=${pg_user})"
  for _ in {1..60}; do
    if $COMPOSE exec -T db pg_isready -U "${pg_user}" -d "${pg_db}" >/dev/null 2>&1; then
      echo "[import] PostgreSQL is ready"
      return 0
    fi
    sleep 1
  done

  echo "[import] PostgreSQL did not become ready in time"
  exit 1
}

DB_ENGINE="$(read_env_var DB_ENGINE)"
DB_ENGINE="${DB_ENGINE,,}"
DB_ENGINE="${DB_ENGINE:-sqlite}"

if [[ "${DB_ENGINE}" != "postgres" ]]; then
  echo "[import] DB_ENGINE must be postgres for import. Current: ${DB_ENGINE}"
  exit 1
fi

if [[ $# -gt 0 ]]; then
  DUMP_PATH="$1"
else
  DUMP_PATH="$(ls -1t backups/migration/sqlite_dump_*.json 2>/dev/null | head -n1 || true)"
fi

if [[ -z "${DUMP_PATH}" || ! -f "${DUMP_PATH}" ]]; then
  echo "[import] Dump file not found. Pass path explicitly, for example:"
  echo "         bash deploy/scripts/import-postgres-data.sh backups/migration/sqlite_dump_YYYYMMDD_HHMMSS.json"
  exit 1
fi

mkdir -p backups/migration
SEQ_SQL_PATH="backups/migration/sequence_reset_$(date +%Y%m%d_%H%M%S).sql"

echo "[import] Start db and web services"
$COMPOSE up -d db
wait_for_postgres
$COMPOSE up -d web

echo "[import] Apply migrations on PostgreSQL"
$COMPOSE exec -T web python manage.py migrate --noinput

echo "[import] Copy dump into web container"
$COMPOSE exec -T web sh -lc "cat > /tmp/sqlite_dump.json" < "${DUMP_PATH}"

echo "[import] Load data into PostgreSQL"
$COMPOSE exec -T web python manage.py loaddata /tmp/sqlite_dump.json
$COMPOSE exec -T web rm -f /tmp/sqlite_dump.json

echo "[import] Reset PostgreSQL sequences"
$COMPOSE exec -T web python manage.py sqlsequencereset "${APPS[@]}" > "${SEQ_SQL_PATH}"
$COMPOSE exec -T db sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "${SEQ_SQL_PATH}"

echo "[import] Run verification checks"
$COMPOSE exec -T web python manage.py showmigrations
$COMPOSE exec -T web python manage.py check --deploy

echo "[import] Done. Sequence SQL: ${SEQ_SQL_PATH}"
