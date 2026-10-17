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
| 23 | Shopee không có API trả tổng tiền theo ngày độc lập với chi tiết đơn | `shopee__daily_totals.gross_amount` để trống; `reconcile_daily_totals` bỏ qua so tiền khi nguồn để trống, vẫn so số đơn (01 §1.1 "khi nền tảng cho phép") | 01 §1.1, §3; 02 §5 |
| 24 | Chỗ đặt chữ ký và đổi mã OAuth dùng chung cho API và connector | `dx_common.marketplace`; khóa ứng dụng `dx-<source>-app` có thêm trường tùy chọn `api_base`, `auth_base` (môi trường thử của sàn), TikTok cần `service_id` | 01 §2.2, 05 §6.7 |
| 25 | Khung dlt cho connector | `connectors/common/load.py`: mọi bảng `merge` theo khóa nguồn + `_dx_source_account`, kiểu cột khai báo đầy đủ, bảng chưa có dữ liệu vẫn được tạo rỗng để dbt đọc; con trỏ trong dlt state theo tài khoản; quét lại đơn mở đọc từ raw. Nguồn `portal` giữ cách ghi ảnh chụp đầy đủ qua `Warehouse.write_rows` (kết quả như `sql_database` + replace, không cần dlt đọc Postgres) | 01 §1, §2, §7 |
| 26 | Callback OAuth khi `state` sai hoặc đổi mã lỗi | Chuyển hướng về cổng với `connect_error=<mã>` thay vì trả JSON, vì người dùng đang ở trình duyệt | 05 §6.7 |
| 27 | Spec 08 §1 nêu aiogram 3 nhưng §9 yêu cầu test bằng `respx` (aiogram dùng aiohttp, respx không chặn được) | Bot gọi Bot API trực tiếp qua `httpx` (`bot/telegram_api.py`), cùng cấu trúc webhook/lệnh/callback; bỏ phụ thuộc aiogram | 08 §1, §9 |
| 28 | Màn `/ops/reports` cần danh sách mọi khách nhưng `GET /v1/reports` gắn với một khách | Thêm `GET /v1/ops/reports` (quyền `ops.read`), lọc theo trạng thái và khách | 06 §4.4, §10 |
| 29 | Nút "Xem báo cáo" của `/report` cần token mở mà token gốc chỉ lưu dạng hash | Người nhận riêng `telegram_cmd:<chat_id>` với token tất định HMAC(INTERNAL_API_TOKEN, báo cáo + liên kết), lưu hash như mọi token | 08 §4, 06 §4.6 |
| 30 | Ba số chính cho member có allowlist và nhóm Telegram có phạm vi | Tính bằng ngữ cảnh nội bộ của đúng khách rồi che số ngoài phạm vi (`value = null`, "Ngoài phạm vi được xem" / "— (ngoài phạm vi của nhóm)") thay vì báo lỗi | 03 §5, 08 §3.6 |
| 31 | Mở báo cáo qua `/r/<token>` khi người nhận đã mở trên cổng trước đó | Mỗi lần mở ghi một dòng `report_opens`; màn vận hành hiện lần mở đầu tiên và kênh của lần đó | 06 §4.6 |
| 32 | File mẫu kiểm tra sức khỏe không có tiền hoàn nên doanh thu thực nhận lệch tới 3,8% so với API (07 §10 yêu cầu ≤ 1%) | File xuất đơn mẫu có thêm cột hoàn tiền theo dòng (như file xuất thật của sàn: số tiền hoàn, ngày hoàn, phí vận chuyển trả hàng); adapter sinh `<sàn>_file__returns`, staging `stg_<sàn>_file__returns` (lý do `other`). Kết quả khớp `demo_seller` tuyệt đối | 07 §4.1, §10 |
| 33 | Dạng bảng raw của nguồn file | Adapter chuẩn hóa về `orders`, `order_lines`, `fees`, `returns`, `ad_insights_daily`, `product_costs` (cột cố định, thỏa hợp đồng spec 01 §1); staging `*_file` dùng macro chung `dx_file_*` và seed ánh xạ của sàn tương ứng (thêm trạng thái tiếng Việt của Shopee). Lượt kiểm tra chạy một lần nên ghi bảng bằng `Warehouse.write_rows` (thay toàn bộ) thay vì dlt | 07 §4.2 |
| 34 | Chỉ số quảng cáo (`platform_vs_actual_gap`, `roas_platform`) thuộc gói Agency, lượt kiểm tra là gói Seller | Phần "chênh lệch nguồn" của kết quả đọc cùng dữ liệu của lượt kiểm tra với góc nhìn gói Agency (cùng bộ máy, cùng định nghĩa) | 07 §6 |
| 35 | Thời điểm sao chép raw sang khách mới (07 §8 bước 2) | Job Dagster `healthcheck_convert` (chạy tay sau khi bootstrap khách), chỉ chạy khi người gửi đã đồng ý; xong thì xóa dữ liệu tạm | 07 §8 |
| 36 | Ảnh chụp "Xuất file này ở đâu" | Hướng dẫn từng bước dạng chữ trong `apps/web/lib/hc-guides.ts`; ảnh đặt ở `public/hc-guides/<kind>.png` khi có. Có file mẫu giá vốn trống `public/hc-guides/gia-von-mau.xlsx` | 07 §2 |
