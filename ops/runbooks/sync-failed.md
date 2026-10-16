# Runbook – `sync.failed` (spec 04 §3.2, §4.3)

| `reason` | Kiểm tra | Cách xử lý |
|---|---|---|
| `auth_revoked` | Token sàn hết hạn hoặc bị thu hồi | `marketplace-oauth.md` bước 2 |
| `rate_limited` | Nền tảng giới hạn tần suất | Chờ lần chạy kế tiếp; giảm tần suất `schedule.sync` nếu lặp lại |
| `api_error` | API nguồn trả lỗi; xem `detail` | Thử chạy lại ở `/ops/tenants/<id>`; đối chiếu tài liệu API ghi trong README connector |
| `windsor_stale` | Windsor chưa nạp xong | Kiểm tra lịch và lỗi trên Windsor (`windsor-setup.md`) |
| `override_invalid` | File ghi đè sai cột hoặc trạng thái | Sửa `tenants/overrides/<id>_status_map.csv` |
| `dbt_error` | Model lỗi khi chạy | Xem `run_results.json` trong `METADATA_BUCKET/<tenant>/<run_id>/` |
| `swap_failed` | Không hoán đổi được marts | Kiểm tra quyền dataset; chạy lại |
| `cube_refresh_failed` | Cube không làm mới được | Kiểm tra container `cube`, log `docker compose logs cube` |

Sau khi sửa: "Chạy lại" ở `/ops/tenants/<id>` (phát `pipeline.requested`).
