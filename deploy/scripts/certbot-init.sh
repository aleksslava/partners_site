#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <domain> <email>"
  exit 1
fi

DOMAIN="$1"
EMAIL="$2"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

COMPOSE="docker compose --env-file deploy/env/prod.env"

ENV_DOMAIN="$(awk -F= '$1=="DOMAIN"{print $2}' deploy/env/prod.env | tail -n1 | tr -d '\r')"
if [[ -n "${ENV_DOMAIN}" && "${ENV_DOMAIN}" != "${DOMAIN}" ]]; then
  echo "[certbot] Warning: DOMAIN in prod.env (${ENV_DOMAIN}) differs from input (${DOMAIN})"
fi

mkdir -p \
  "data/letsencrypt/live/${DOMAIN}" \
  "data/letsencrypt/archive/${DOMAIN}" \
  "data/certbot-www" \
  "data/static" \
  "data/media" \
  "data/db"
touch data/amocrm_tokens.env

if [[ ! -f data/letsencrypt/options-ssl-nginx.conf || ! -f data/letsencrypt/ssl-dhparams.pem ]]; then
  echo "[certbot] Download recommended TLS params"
  curl -fsSL https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf -o data/letsencrypt/options-ssl-nginx.conf
  curl -fsSL https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem -o data/letsencrypt/ssl-dhparams.pem
fi

RENEWAL_CONF="data/letsencrypt/renewal/${DOMAIN}.conf"
if [[ -d "data/letsencrypt/live/${DOMAIN}" && ! -f "${RENEWAL_CONF}" ]]; then
  echo "[certbot] Cleanup unmanaged certificate directories for ${DOMAIN}"
  rm -rf "data/letsencrypt/live/${DOMAIN}" "data/letsencrypt/archive/${DOMAIN}"
  mkdir -p "data/letsencrypt/live/${DOMAIN}" "data/letsencrypt/archive/${DOMAIN}"
fi

DUMMY_CERT_DIR="data/letsencrypt/live/${DOMAIN}"
if [[ ! -f "${DUMMY_CERT_DIR}/fullchain.pem" || ! -f "${DUMMY_CERT_DIR}/privkey.pem" ]]; then
  echo "[certbot] Create temporary self-signed certificate for nginx boot"
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout "${DUMMY_CERT_DIR}/privkey.pem" \
    -out "${DUMMY_CERT_DIR}/fullchain.pem" \
    -subj "/CN=${DOMAIN}"
fi

echo "[certbot] Start nginx for ACME challenge"
$COMPOSE up -d web nginx

if [[ ! -f "${RENEWAL_CONF}" ]]; then
  echo "[certbot] Remove temporary certificate files before issuing Let's Encrypt cert"
  rm -rf "data/letsencrypt/live/${DOMAIN}" "data/letsencrypt/archive/${DOMAIN}"
  rm -f "${RENEWAL_CONF}"
fi

echo "[certbot] Request Let's Encrypt certificate"
docker run --rm \
  -v "${ROOT_DIR}/data/letsencrypt:/etc/letsencrypt" \
  -v "${ROOT_DIR}/data/certbot-www:/var/www/certbot" \
  certbot/certbot certonly \
  --webroot -w /var/www/certbot \
  --cert-name "${DOMAIN}" \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive

echo "[certbot] Reload nginx with real certificate"
$COMPOSE restart nginx

echo "[certbot] Done"
