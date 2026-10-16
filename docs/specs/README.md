# DataxLand – Bộ specs

Specs là đầu vào trực tiếp cho Claude Code. Mỗi spec mô tả một phần hệ thống đến mức có thể cài đặt và kiểm thử: đường dẫn file, schema, giao diện, hành vi, tiêu chí hoàn thành.

Nguồn sự thật theo thứ tự ưu tiên khi có mâu thuẫn:

1. Spec của phần đang làm
2. `docs/specs/00-foundation.md`
3. `docs/prd.md`
4. `docs/architecture.md`

Gặp mâu thuẫn thì dừng lại, ghi vào `docs/adr/` và hỏi chủ dự án, không tự chọn.

## Danh sách

| Spec | Hệ thống | Yêu cầu PRD | Giai đoạn |
|---|---|---|---|
| [00-foundation.md](00-foundation.md) | Tất cả | NFR-01..12 | 1 |
| [01-ingestion.md](01-ingestion.md) | S1 | FR-ING-01..09 | 1 (FR-ING-09: 2) |
| [02-transform-and-quality.md](02-transform-and-quality.md) | S1 | FR-MOD-01..05, FR-DQ-01..04 | 1 |
| [03-semantic-layer.md](03-semantic-layer.md) | S2 | FR-MET-01..08 | 1 |
| [04-ops-and-orchestration.md](04-ops-and-orchestration.md) | S4 | FR-OPS-01..09 | 1 (một phần: 2) |
| [05-api-and-auth.md](05-api-and-auth.md) | S6, S4 | FR-AUTH-01..05, FR-INP-01..05 | 1 |
| [06-portal.md](06-portal.md) | S6 | FR-REP-01..07, FR-DSH-01..05, FR-DEC-01..04, FR-AGY-01..03 | 1 |
| [07-health-check.md](07-health-check.md) | S5 | FR-HC-01..05 | 1 |
| [08-telegram-bot.md](08-telegram-bot.md) | S6b | FR-TG-01..08 | 1 (FR-TG-06: 2) |
| [09-ai-layer.md](09-ai-layer.md) | S7 | FR-AI-01..03, FR-AGT-01 | 2 |
| [10-identity-resolution.md](10-identity-resolution.md) | S3 | FR-ID-01..02 | 2 |

FR-BMK-01 (so sánh ngành, giai đoạn 3) chưa có spec; viết khi bắt đầu giai đoạn 3.

## Thứ tự xây cho giai đoạn 1

Thứ tự này khớp với các mốc trong PRD mục 12.

| Bước | Mốc | Làm gì | Spec |
|---|---|---|---|
| 1 | M0 | Khung repo, tooling, CI, docker compose, khách giả lập | 00 |
| 2 | M0 | Postgres, Alembic, FastAPI khung, Firebase Auth, ma trận quyền | 05 |
| 3 | M0 | Sổ đăng ký khách, sự kiện, Dagster khung với khách giả lập | 04 |
| 4 | M0 | dbt: staging từ dữ liệu mẫu, core, marts, test | 02 |
| 5 | M0 | Thư viện chỉ số, `build.py`, Cube đa khách, `/v1/metrics/query` | 03 |
| 6 | M1 | Connector Shopee, TikTok Shop, tỷ giá, nguồn `portal`; cấu hình Windsor | 01 |
| 7 | M2 | Cổng: dashboard, sổ tay, nhập giá vốn và ngân sách | 06, 05 |
| 8 | M3 | Báo cáo tuần, lớp thông báo, Telegram bot | 06, 04, 08 |
| 9 | M3 | Kiểm tra sức khỏe dữ liệu | 07 |
| 10 | M3 | Màn hình vận hành, trang agency cơ bản | 06 |
| 11 | M4 | Lazada, xóa dữ liệu người mua, nhóm Telegram, giới hạn tần suất | 01, 04, 08 |

Mỗi bước kết thúc khi đạt "Tiêu chí hoàn thành" trong spec tương ứng và CI xanh.
