# partners_site

Проект интернет-магазина на Django 5 + Docker Compose (Gunicorn + Nginx) с поддержкой двух БД:
- SQLite (fallback/rollback)
- PostgreSQL (production target)

Подробный деплой и полный runbook миграции: `deploy/README.md`.

## Обновление кода на сервере

Текущая схема:
- пользователь: `slava`
- директория проекта: `/opt/partners_site`
- ветка: `main`

```bash
ssh slava@<SERVER_IP>
cd /opt/partners_site

git fetch --all --prune
git checkout main
git pull --ff-only origin main

bash deploy/scripts/release.sh
```

`release.sh` делает:
- пересборку `web` контейнера
- запуск сервисов
- при `DB_ENGINE=postgres`: запуск/ожидание `db`
- `python manage.py migrate --noinput`
- `python manage.py collectstatic --noinput`
- `python manage.py check --deploy`
- запуск `nginx`, если сертификат уже существует

## Конфигурация БД (prod.env)

Основные переменные в `deploy/env/prod.env`:

```env
DB_ENGINE=sqlite|postgres
SQLITE_PATH=/app/data/db.sqlite3

POSTGRES_DB=partners_site
POSTGRES_USER=partners_site
POSTGRES_PASSWORD=change-me
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=60
```

По умолчанию используется `sqlite`, для PostgreSQL установите `DB_ENGINE=postgres`.

## Полезные команды после релиза

```bash
cd /opt/partners_site
docker compose --env-file deploy/env/prod.env ps
docker compose --env-file deploy/env/prod.env logs --tail=100 web
docker compose --env-file deploy/env/prod.env logs --tail=100 nginx
```

## Миграция SQLite -> PostgreSQL

Ключевые скрипты:

```bash
# Полный безопасный retry миграции одним запуском
bash deploy/scripts/retry-sqlite-to-postgres.sh

# Экспорт данных из SQLite в JSON (dumpdata)
bash deploy/scripts/export-sqlite-data.sh

# Импорт JSON в PostgreSQL + migrate + reset sequence + checks
bash deploy/scripts/import-postgres-data.sh backups/migration/sqlite_dump_YYYYMMDD_HHMMSS.json

# Снимок количества строк по критичным таблицам
bash deploy/scripts/report-table-counts.sh backups/migration/counts_before.tsv
```

Полный пошаговый сценарий (rehearsal, cutover, rollback, smoke-checks): `deploy/README.md`.

## Бэкапы

`deploy/scripts/backup.sh` выполняет:
- SQLite backup (`backups/sqlite`, хранение 14 дней)
- PostgreSQL backup через `pg_dump` (`backups/postgres`, хранение 14 дней, при `DB_ENGINE=postgres`)
- media backup (`backups/media`, хранение 30 дней)

Рекомендуемый cron:

```bash
# daily backups
0 3 * * * cd /opt/partners_site && bash deploy/scripts/backup.sh >> /var/log/partners_backup.log 2>&1

# cert renew twice a day
0 4,16 * * * cd /opt/partners_site && bash deploy/scripts/certbot-renew.sh >> /var/log/partners_certbot.log 2>&1
```

## TLS-сертификат вручную

```bash
cd /opt/partners_site
bash deploy/scripts/certbot-renew.sh
```
