# Nhật ký thử khôi phục Postgres (NFR-06, spec 00 §8.3)

Mỗi tháng chạy thử khôi phục bản sao lưu mới nhất vào một database tạm và ghi kết quả vào bảng dưới.

## Cách làm

```bash
# Trên VM prod
LATEST=$(gsutil ls gs://dx-backup-prod/postgres/dx-*.dump | sort | tail -1)
docker compose -f infra/compose/docker-compose.yml --env-file .env exec -T postgres \
  psql -U dx -c "drop database if exists dx_restore_test" -c "create database dx_restore_test"
gsutil cat "$LATEST" | docker compose -f infra/compose/docker-compose.yml --env-file .env exec -T postgres \
  pg_restore -U dx -d dx_restore_test --no-owner
docker compose -f infra/compose/docker-compose.yml --env-file .env exec -T postgres \
  psql -U dx -d dx_restore_test -c "select count(*) from tenants" -c "select count(*) from reports"
# So số dòng với database dx đang chạy, rồi xóa database tạm.
```

## Kết quả

| Ngày | Bản sao lưu | Thời gian khôi phục | Số dòng `tenants` / `reports` khớp | Người chạy | Ghi chú |
|---|---|---|---|---|---|
| | | | | | |
