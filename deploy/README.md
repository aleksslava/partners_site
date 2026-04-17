# VDS deployment (Ubuntu 24.04, Docker Compose, SQLite/PostgreSQL)

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
mkdir -p data/db data/postgres data/media data/static data/certbot-www data/letsencrypt
```

Edit `deploy/env/prod.env` and set real values (`DOMAIN`, Django secret, amoCRM credentials, DB settings).

## 3) First release (SQLite or PostgreSQL)

- For SQLite keep:
  - `DB_ENGINE=sqlite`
  - `SQLITE_PATH=/app/data/db.sqlite3`

- For PostgreSQL set:
  - `DB_ENGINE=postgres`
  - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST=db`, `POSTGRES_PORT=5432`

```bash
bash deploy/scripts/release.sh
```

## 4) Issue TLS certificate

```bash
bash deploy/scripts/certbot-init.sh example.com admin@example.com
bash deploy/scripts/release.sh
```

## 5) Verify

```bash
docker compose --env-file deploy/env/prod.env ps
curl -I http://example.com
curl -I https://example.com
docker compose --env-file deploy/env/prod.env exec web python manage.py check --deploy
```

---

## SQLite -> PostgreSQL migration runbook (short downtime)

### Fast path (one command retry)

If you already had a failed import and need a safe retry end-to-end:

```bash
bash deploy/scripts/retry-sqlite-to-postgres.sh
```

Optional custom env path:

```bash
bash deploy/scripts/retry-sqlite-to-postgres.sh deploy/env/prod.env
```

### A) Rehearsal (required)

1. Keep production on SQLite (`DB_ENGINE=sqlite`).
2. Copy prod SQLite to a rehearsal environment.
3. Run full dry run: export JSON -> migrate PostgreSQL -> import JSON -> reset sequences -> checks.
4. Record timing for each step.

### B) Prepare before cutover window

```bash
cd /opt/partners_site
mkdir -p backups/sqlite backups/migration
```

1. Temporarily pause cron jobs for deploy/backup.
2. Backup SQLite file and checksum:

```bash
TS=$(date +%Y%m%d_%H%M%S)
cp data/db/db.sqlite3 backups/sqlite/db_${TS}.sqlite3
sha256sum backups/sqlite/db_${TS}.sqlite3 > backups/sqlite/db_${TS}.sqlite3.sha256
```

3. Save row counts before cutover:

```bash
bash deploy/scripts/report-table-counts.sh backups/migration/counts_before_$(date +%Y%m%d_%H%M%S).tsv
```

### C) Freeze writes

```bash
docker compose --env-file deploy/env/prod.env stop web
# optional (if you want full maintenance page / strict freeze)
docker compose --env-file deploy/env/prod.env stop nginx
```

### D) Export data from SQLite

1. Ensure `deploy/env/prod.env` still has `DB_ENGINE=sqlite`.
2. Start only web for export:

```bash
docker compose --env-file deploy/env/prod.env up -d web
```

3. Export fixtures:

```bash
bash deploy/scripts/export-sqlite-data.sh
# optional custom output path:
# bash deploy/scripts/export-sqlite-data.sh backups/migration/sqlite_dump_manual.json
```

4. Stop web again before final switch:

```bash
docker compose --env-file deploy/env/prod.env stop web
```

### E) Switch config to PostgreSQL

Edit `deploy/env/prod.env`:

- `DB_ENGINE=postgres`
- set valid `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST=db`, `POSTGRES_PORT=5432`

### F) Import into PostgreSQL

```bash
# Start DB and wait until healthy
docker compose --env-file deploy/env/prod.env up -d db

# Load fixtures into PostgreSQL
LATEST_DUMP=$(ls -1t backups/migration/sqlite_dump_*.json | head -n1)
bash deploy/scripts/import-postgres-data.sh "$LATEST_DUMP"
```

Re-run release once data is imported:

```bash
bash deploy/scripts/release.sh
```

### G) Verification after cutover

```bash
# infrastructure
docker compose --env-file deploy/env/prod.env ps

# migrations
docker compose --env-file deploy/env/prod.env exec web python manage.py showmigrations

# deploy checks
docker compose --env-file deploy/env/prod.env exec web python manage.py check --deploy
```

Compare row counts for critical tables before/after cutover:

- `users_user`
- `users_customer`
- `orders_order`
- `orders_cart`
- `shop_product`

```bash
bash deploy/scripts/report-table-counts.sh backups/migration/counts_after_$(date +%Y%m%d_%H%M%S).tsv
```

Run smoke tests:

- admin login
- catalog view
- order create/update flow
- media/static availability

### H) Rollback (if validation fails)

1. Set `DB_ENGINE=sqlite` back in `deploy/env/prod.env`.
2. Ensure original file exists: `data/db/db.sqlite3` (or restore from `backups/sqlite`).
3. Run release:

```bash
bash deploy/scripts/release.sh
```

Leave PostgreSQL data as-is for investigation (`data/postgres`).

---

## Backups and renew tasks (cron)

`deploy/scripts/backup.sh` now does:

- SQLite file backup (kept 14 days, for rollback safety)
- PostgreSQL `pg_dump` backup when `DB_ENGINE=postgres` (kept 14 days)
- media backup (kept 30 days)

Recommended cron:

```bash
# daily backups
0 3 * * * cd /opt/partners_site && bash deploy/scripts/backup.sh >> /var/log/partners_backup.log 2>&1

# cert renew twice a day
0 4,16 * * * cd /opt/partners_site && bash deploy/scripts/certbot-renew.sh >> /var/log/partners_certbot.log 2>&1
```
