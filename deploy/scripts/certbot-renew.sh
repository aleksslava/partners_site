#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE="docker compose --env-file deploy/env/prod.env"

mkdir -p data/letsencrypt data/certbot-www

docker run --rm \
  -v "${ROOT_DIR}/data/letsencrypt:/etc/letsencrypt" \
  -v "${ROOT_DIR}/data/certbot-www:/var/www/certbot" \
  certbot/certbot renew --webroot -w /var/www/certbot --quiet

$COMPOSE exec nginx nginx -s reload

echo "[certbot] Renewal completed"
