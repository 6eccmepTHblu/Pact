#!/bin/bash
# Ежедневный бэкап из cron: дамп БД и отдельно последний хеш журнала.
# По хешу видно, что после восстановления из дампа журнал не подменён.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p backups
day=$(date +%F)
docker compose exec -T db pg_dump -U pact_owner pact | gzip > "backups/pact-$day.sql.gz"
docker compose exec -T app python -m app.cli last-hash > "backups/pact-$day.hash"
find backups -type f -mtime +30 -delete
