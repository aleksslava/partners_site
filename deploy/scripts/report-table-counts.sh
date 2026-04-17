#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="deploy/env/prod.env"
COMPOSE="docker compose --env-file ${ENV_FILE}"
OUT_PATH="${1:-}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[counts] Env file not found: ${ENV_FILE}"
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

  for _ in {1..60}; do
    if $COMPOSE exec -T db pg_isready -U "${pg_user}" -d "${pg_db}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "[counts] PostgreSQL did not become ready in time"
  exit 1
}

DB_ENGINE="$(read_env_var DB_ENGINE)"
DB_ENGINE="${DB_ENGINE,,}"
DB_ENGINE="${DB_ENGINE:-sqlite}"

if [[ "${DB_ENGINE}" != "sqlite" && "${DB_ENGINE}" != "postgres" ]]; then
  echo "[counts] Unsupported DB_ENGINE=${DB_ENGINE}. Use sqlite or postgres"
  exit 1
fi

if [[ "${DB_ENGINE}" == "postgres" ]]; then
  echo "[counts] Ensure PostgreSQL service is running"
  $COMPOSE up -d db
  wait_for_postgres
fi

echo "[counts] Ensure web service is running"
$COMPOSE up -d web

CMD=$'from django.db import connection\n'
CMD+=$'tables = ["users_user", "users_customer", "orders_order", "orders_cart", "shop_product"]\n'
CMD+=$'with connection.cursor() as cursor:\n'
CMD+=$'    for table in tables:\n'
CMD+=$'        cursor.execute(f\'SELECT COUNT(*) FROM \"{table}\"\')\n'
CMD+=$'        count = cursor.fetchone()[0]\n'
CMD+=$'        print(f\"{table}\\t{count}\")\n'

if [[ -n "${OUT_PATH}" ]]; then
  mkdir -p "$(dirname "${OUT_PATH}")"
  $COMPOSE exec -T web python manage.py shell -c "${CMD}" > "${OUT_PATH}"
  echo "[counts] Saved to ${OUT_PATH}"
else
  $COMPOSE exec -T web python manage.py shell -c "${CMD}"
fi
