#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE="docker compose --env-file deploy/env/prod.env"

mkdir -p data/db data/media data/static data/certbot-www data/letsencrypt
touch data/amocrm_tokens.env

echo "[release] Build and start web"
$COMPOSE pull web nginx || true
$COMPOSE build web
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
