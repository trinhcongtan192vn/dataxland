# 0002 – Chi tiết cài đặt tự quyết

- Trạng thái: Accepted (chủ dự án ủy quyền ngày 2026-10-16: "còn lại bạn tự giải quyết")
- Ngày: 2026-10-16

Các mục dưới đây là chỗ tài liệu gốc không nói rõ và việc cài đặt buộc phải chọn, nhưng không đổi hành vi
hay yêu cầu nào trong tài liệu gốc. Mâu thuẫn thật sự hoặc lựa chọn ảnh hưởng sản phẩm vẫn đi theo quy trình
hỏi chủ dự án (constitution, nguyên tắc I).

| # | Chỗ thiếu | Quyết định | Nguồn liên quan |
|---|---|---|---|
| 1 | Email nhận cảnh báo của team không có trong danh sách biến | Thêm `DX_TEAM_EMAIL` | 00 §4.1, 04 §5.3 |
| 2 | URL công khai của API cho callback OAuth và link trong email | Thêm `DX_API_PUBLIC_URL`, `MARKETPLACE_OAUTH_REDIRECT_BASE` | 05 §6.7 |
| 3 | Tên bot cho deep link `t.me/<bot>` | Thêm `TELEGRAM_BOT_USERNAME` | 08 §3.2 |
| 4 | Biến cấu hình Firebase phía trình duyệt | Thêm `NEXT_PUBLIC_FIREBASE_*`, `NEXT_PUBLIC_API_URL` | 06 §1 |
| 5 | Database của Dagster, Metabase | Cùng container Postgres, database `dagster`, `metabase`; biến `DAGSTER_PG_URL` | 00 §7 |
| 6 | Xem email ở local | Thêm service `mailpit` (profile `local`) làm SMTP giả | 00 §7 |
| 7 | Chạy test cần Postgres trên máy không có Docker | `dx_common.testing.ephemeral_postgres`: `DX_TEST_DATABASE_URL` nếu có, nếu không dùng Postgres nhúng `pgserver` | 00 §8.1 |
| 8 | "Hôm nay" cố định cho test | `DX_TODAY`, `DX_NOW` trong `dx_common.timeutil`, chỉ dùng cho test và dữ liệu mẫu | 00 §5 |
| 9 | Dữ liệu mẫu có ngày cố định nhưng demo cần số tuần hiện tại | `make seed-local` sinh lại cùng bộ dữ liệu (seed cố định) với ngày cuối là hôm qua; `--fixed` nạp nguyên `transform/samples/` | 00 §5, 02 §8 |
| 10 | Một bản ghi mẫu cho mỗi phiên bản đơn | Dữ liệu mẫu có cả bản cũ và bản mới của đơn đổi trạng thái, để kiểm tra khử trùng ở staging | 01 §1, 02 §3.1 |
| 11 | Sự kiện nội bộ cần thêm | `tenant.bootstrap_required`, `tenant.config_invalid`, `report.built`, `healthcheck.failed`, `pipeline.requested`, `identity.changed` | 04 §1.3, 05 §6.9, 06 §4.2, 07 §5, 10 §6 |
| 12 | Đếm số lần xử lý lỗi của sự kiện | Cột `attempts`, `dead` trong `event_dead_letters` | 04 §4.2 |
| 13 | Thứ tự commit lệch của outbox | `consume` quét lại 10 phút trước offset, dựa vào `event_processed` để không trùng | 04 §4.2, architecture §11.2 |
| 14 | `net_amount` khi sàn trợ giá | `discount_amount` = giảm giá của shop + của sàn; `net_amount` = `gross` − giảm giá do shop chịu (giảm giá do sàn chịu vẫn về shop). Chủ dự án xác nhận ngày 2026-10-16 | 02 §3.2, architecture §6.3 |
| 15 | Bảng phụ cho hành vi đã mô tả | `notification_groups` (gộp cảnh báo 6 giờ), `channel_health` (Telegram lỗi 30 phút), `metric_anomalies` (chống phát trùng), `rate_counters` (giới hạn tần suất), `identity_matches` (spec 10), `tenant_costs`, `tenant_hours` (FR-OPS-06) | 04 §5.4, 03 §8, 05 §8 |
| 16 | Mời owner cho khách mới | `POST /v1/members/invitations` nhận `role: owner` khi người gọi là `data_lead` (`users.manage`); owner chỉ mời được member | 05 §4, §5.1 |
| 17 | Nhận lời mời | Đăng nhập lần đầu tự nhận lời mời trùng email; trang `/invite/<token>` gọi `POST /v1/invitations/accept`, yêu cầu email đăng nhập trùng email được mời | 05 §3.1, §5.1 |
| 18 | Chiều để hiện tên SKU và tìm SKU thiếu giá vốn | Thêm chiều `sku` (`seller_sku`) và `product_name` trên mart dòng đơn; chỉ số ẩn `missing_cogs_revenue` | 03 §2.3, 05 §6.3, 06 §3.1 |
| 19 | Chỉ số có cách tính khác nhau theo mart (vd. `ad_spend` ở ad_daily và budget_monthly) và tiến độ ngân sách cần chi kỳ vọng tới hôm nay | Trường mở rộng `variants` trong YAML chỉ số (mỗi mart một `measure`), tính vào trường tính toán khi kiểm phiên bản; cột `budget_expected_mtd_vnd` trên `mrt_agency__budget_monthly` | 03 §2.1, §3.3, §6 |
| 20 | Cube local trên Windows | Driver `cube/local_duckdb.js` mở file DuckDB chỉ đọc cho từng truy vấn (để dbt ghi được khi Cube chạy), phiên ở UTC; tắt pre-aggregation trên win32 vì Cube Store lỗi đường dẫn. Dev/prod dùng BigQuery, không ảnh hưởng | 00 §4, 03 §10 |
| 21 | "Bản đang chạy" để so khi phát `metric.released` | `ops/release_metrics.py` giữ ảnh chụp phiên bản ở `.local/metrics_released.json` trên VM; lần đầu chỉ ghi mốc, không phát sự kiện; chạy trong bước deploy | 03 §6 |
| 22 | Mã lỗi khi Cube từ chối token | `cube.js` ném `CubejsHandlerError(403)` để thiếu `tenant_id` hoặc prefix không khớp trả 403, không phải 500 | 03 §10.1, §11 |
