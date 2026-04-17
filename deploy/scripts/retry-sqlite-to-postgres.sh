#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="deploy/env/prod.env"
if [[ $# -gt 0 ]]; then
  ENV_FILE="$1"
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[retry] Env file not found: ${ENV_FILE}"
  echo "[retry] Usage: bash deploy/scripts/retry-sqlite-to-postgres.sh [path/to/prod.env]"
  exit 1
fi

COMPOSE="docker compose --env-file ${ENV_FILE}"
TS="$(date +%Y%m%d_%H%M%S)"

DUMP="backups/migration/sqlite_dump_retry_${TS}.json"
ENV_BAK="backups/migration/prod.env.before_retry_${TS}"
COUNT_BEFORE="backups/migration/counts_before_${TS}.tsv"
COUNT_AFTER="backups/migration/counts_after_${TS}.tsv"

set_env_var() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "${ENV_FILE}"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

read_env_var() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d= -f2- | tr -d '\r' || true
}

on_error() {
  local line="$1"
  echo "[retry] Failed at line ${line}"
  echo "[retry] To rollback quickly:"
  echo "        cp \"${ENV_BAK}\" \"${ENV_FILE}\""
  echo "        bash deploy/scripts/release.sh"
}

mkdir -p backups/sqlite backups/postgres backups/migration data/postgres
cp "${ENV_FILE}" "${ENV_BAK}"
trap 'on_error $LINENO' ERR

echo "[retry] Backup current sqlite and env"
cp data/db/db.sqlite3 "backups/sqlite/db_${TS}.sqlite3"
sha256sum "backups/sqlite/db_${TS}.sqlite3" > "backups/sqlite/db_${TS}.sqlite3.sha256"

if [[ -n "$(find data/postgres -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)" ]]; then
  tar -czf "backups/postgres/pgdata_before_retry_${TS}.tar.gz" -C data postgres
fi

echo "[retry] Switch to sqlite for source snapshot"
set_env_var DB_ENGINE sqlite

echo "[retry] Freeze writes"
$COMPOSE stop nginx web || true

echo "[retry] Save counts before migration"
bash deploy/scripts/report-table-counts.sh "${COUNT_BEFORE}"

echo "[retry] Export sqlite dump without natural-primary"
$COMPOSE up -d web
$COMPOSE exec -T web \
  python manage.py dumpdata \
  --natural-foreign \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude admin.logentry \
  > "${DUMP}"
test -s "${DUMP}"
$COMPOSE stop web

echo "[retry] Switch to postgres target"
set_env_var DB_ENGINE postgres

for key in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_HOST POSTGRES_PORT; do
  value="$(read_env_var "${key}")"
  if [[ -z "${value}" ]]; then
    echo "[retry] Missing ${key} in ${ENV_FILE}"
    exit 1
  fi
done

echo "[retry] Recreate postgres data directory"
$COMPOSE down
mkdir -p data/postgres
find data/postgres -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +

echo "[retry] Import into postgres"
bash deploy/scripts/import-postgres-data.sh "${DUMP}"

echo "[retry] Final release"
bash deploy/scripts/release.sh

echo "[retry] Verification"
bash deploy/scripts/report-table-counts.sh "${COUNT_AFTER}"
$COMPOSE ps
$COMPOSE exec -T web python manage.py showmigrations
$COMPOSE exec -T web python manage.py check --deploy
diff -u "${COUNT_BEFORE}" "${COUNT_AFTER}" || true

echo "[retry] DONE"
echo "[retry] Dump: ${DUMP}"
echo "[retry] Env backup: ${ENV_BAK}"
