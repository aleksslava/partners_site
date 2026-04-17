#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="deploy/env/prod.env"
COMPOSE="docker compose --env-file ${ENV_FILE}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[release] Env file not found: ${ENV_FILE}"
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

  echo "[release] Waiting for PostgreSQL (db=${pg_db}, user=${pg_user})"
  for _ in {1..60}; do
    if $COMPOSE exec -T db pg_isready -U "${pg_user}" -d "${pg_db}" >/dev/null 2>&1; then
      echo "[release] PostgreSQL is ready"
      return 0
    fi
    sleep 1
  done

  echo "[release] PostgreSQL did not become ready in time"
  exit 1
}

DB_ENGINE="$(read_env_var DB_ENGINE)"
DB_ENGINE="${DB_ENGINE,,}"
DB_ENGINE="${DB_ENGINE:-sqlite}"

if [[ "${DB_ENGINE}" != "sqlite" && "${DB_ENGINE}" != "postgres" ]]; then
  echo "[release] Unsupported DB_ENGINE=${DB_ENGINE}. Use sqlite or postgres"
  exit 1
fi

mkdir -p data/db data/postgres data/media data/static data/certbot-www data/letsencrypt
touch data/amocrm_tokens.env

echo "[release] Build and start web"
$COMPOSE pull web nginx db || true
$COMPOSE build web

if [[ "${DB_ENGINE}" == "postgres" ]]; then
  echo "[release] Start PostgreSQL service"
  $COMPOSE up -d db
  wait_for_postgres
fi

$COMPOSE up -d web

echo "[release] Apply migrations"
$COMPOSE exec web python manage.py migrate --noinput

echo "[release] Collect static"
$COMPOSE exec web python manage.py collectstatic --noinput

echo "[release] Django deploy checks"
$COMPOSE exec web python manage.py check --deploy

DOMAIN="$(awk -F= '$1=="DOMAIN"{print $2}' deploy/env/prod.env | tail -n1 | tr -d '\r')"
CERT_PATH="data/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [[ -n "${DOMAIN}" && -f "${CERT_PATH}" ]]; then
  echo "[release] Start nginx"
  $COMPOSE up -d nginx
else
  echo "[release] Skip nginx: TLS certificate not found for DOMAIN=${DOMAIN}"
  echo "[release] Run deploy/scripts/certbot-init.sh <domain> <email> before enabling nginx"
fi

echo "[release] Services status"
$COMPOSE ps
