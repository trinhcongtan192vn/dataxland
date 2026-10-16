#!/usr/bin/env bash
# Sao lưu Postgres hằng ngày lúc 02:00 giờ Việt Nam lên gs://dx-backup-prod/postgres/, giữ 30 ngày (spec 00 §8.3).
# Cài trên VM prod bằng cron:  0 19 * * * /srv/dataxland/ops/backup_postgres.sh   (19:00 UTC = 02:00 VN)
# Bucket đặt lifecycle xóa object cũ hơn 30 ngày.
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BUCKET=${BACKUP_BUCKET:-gs://dx-backup-prod/postgres}
COMPOSE="docker compose -f infra/compose/docker-compose.yml --env-file .env"
for db in dx dagster; do
  $COMPOSE exec -T postgres pg_dump -U dx -Fc "$db" | gsutil cp - "$BUCKET/$db-$STAMP.dump"
done
echo "Đã sao lưu $STAMP lên $BUCKET"
