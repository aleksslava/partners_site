# VDS deployment (Ubuntu 24.04, Docker Compose, SQLite)

## 1) Prepare server

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl

# Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker
```

## 2) Clone project and prepare env files

```bash
git clone <your-repo-url> /opt/partners_site
cd /opt/partners_site

cp deploy/env/prod.env.example deploy/env/prod.env
cp deploy/env/amocrm_tokens.env.example data/amocrm_tokens.env
mkdir -p data/db data/media data/static data/certbot-www data/letsencrypt
```

Edit `deploy/env/prod.env` and set real values (`DOMAIN`, Django secret, amoCRM credentials).

## 3) Copy current data

```bash
# copy SQLite and media from current environment
cp /path/from/current/server/db.sqlite3 data/db/db.sqlite3
rsync -a /path/from/current/server/products/ data/media/
```

## 4) First release

```bash
bash deploy/scripts/release.sh
```

## 5) Issue TLS certificate

```bash
bash deploy/scripts/certbot-init.sh example.com admin@example.com
bash deploy/scripts/release.sh
```

## 6) Verify

```bash
docker compose --env-file deploy/env/prod.env ps
curl -I http://example.com
curl -I https://example.com
docker compose --env-file deploy/env/prod.env exec web python manage.py check --deploy
```

## 7) Backup and renew tasks (cron)

```bash
# daily backups
0 3 * * * cd /opt/partners_site && bash deploy/scripts/backup.sh >> /var/log/partners_backup.log 2>&1

# cert renew twice a day
0 4,16 * * * cd /opt/partners_site && bash deploy/scripts/certbot-renew.sh >> /var/log/partners_certbot.log 2>&1
```
