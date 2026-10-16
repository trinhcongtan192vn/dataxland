# Spec 00 – Nền móng

Phạm vi: cấu trúc repo, công cụ, quy ước chung, môi trường, cấu hình, khách giả lập, CI, triển khai giai đoạn 1. Mọi spec khác giả định phần này đã có.

Yêu cầu liên quan: NFR-01..12.

---

## 1. Cấu trúc repo

Monorepo `dataxland/`. Thư mục nào chưa dùng ở giai đoạn 1 vẫn tạo với `README.md` một dòng để giữ cấu trúc.

```
dataxland/
  CLAUDE.md
  pyproject.toml              # uv workspace gốc
  uv.lock
  package.json                # pnpm workspace gốc
  pnpm-workspace.yaml
  .env.example
  Makefile
  apps/
    web/                      # Next.js
  libs/
    dx_common/                # thư viện Python dùng chung
  services/
    api/                      # FastAPI
    telegram_bot/
    mcp/                      # GĐ2
    identity_worker/          # GĐ2
  pipelines/                  # Dagster + dlt
  transform/                  # dbt
  semantic/                   # thư viện chỉ số, build.py, model Cube sinh ra
  cube/                       # cấu hình runtime của Cube (cube.js)
  tenants/                    # file cấu hình khách
  knowledge/
  agents/                     # GĐ2
  ai/                         # GĐ2
  ops/                        # script vận hành, runbook
  infra/
    compose/
    terraform/                # GĐ2
  docs/
```

### 1.1 `libs/dx_common`

Thư viện Python dùng chung cho mọi service và pipeline. Không service nào được tự viết lại những thứ có ở đây.

| Module | Nội dung |
|---|---|
| `dx_common.config` | Đọc cấu hình từ biến môi trường bằng `pydantic-settings`; một class `Settings` duy nhất |
| `dx_common.logging` | Log JSON ra stdout, có `tenant_id`, `request_id`, `run_id` khi có |
| `dx_common.tenants` | Model Pydantic của file cấu hình khách (spec 04 mục 1), hàm đọc và kiểm tra |
| `dx_common.events` | Model envelope sự kiện, hàm `publish()` và `consume()` (spec 04 mục 4) |
| `dx_common.db` | Engine SQLAlchemy và session cho Postgres control plane |
| `dx_common.secrets` | Đọc và ghi Secret Manager; ở `local` đọc từ file `.secrets/` |
| `dx_common.money` | Kiểu và hàm định dạng tiền VND |
| `dx_common.timeutil` | Hàm chuyển giữa UTC và `Asia/Ho_Chi_Minh`, tính tuần ISO theo giờ Việt Nam |

## 2. Công cụ và phiên bản

| Thành phần | Công cụ |
|---|---|
| Python | 3.12, quản lý bằng `uv` (workspace) |
| Lint, format Python | `ruff` (lint + format), `mypy --strict` cho `libs/` và `services/` |
| Test Python | `pytest`, `pytest-asyncio`, `respx` cho HTTP giả lập |
| Node | 22 LTS, `pnpm` |
| Web | Next.js 15 (App Router), TypeScript strict, Tailwind CSS |
| Lint, test web | `eslint`, `prettier`, `vitest`, `playwright` |
| SQL | `sqlfluff` với dialect `bigquery` cho `transform/`, cấu hình bỏ qua Jinja |
| Database control plane | Postgres 16, SQLAlchemy 2, Alembic |
| Điều phối | Dagster, `dagster-dbt`, `dagster-dlt` |
| Kéo dữ liệu | `dlt` |
| Biến đổi | `dbt-core`, `dbt-bigquery`, `dbt-duckdb`, gói `elementary` |
| Lớp ngữ nghĩa | Cube (self-hosted, image `cubejs/cube`) |
| Container | Docker, Docker Compose v2 |

Mọi phiên bản cụ thể được ghim trong `uv.lock`, `pnpm-lock.yaml`, `transform/packages.yml` và tag image trong `infra/compose/docker-compose.yml`. Khi nâng phiên bản lớn, ghi một ADR.

## 3. Quy ước chung

### 3.1 Đặt tên

| Đối tượng | Quy ước | Ví dụ |
|---|---|---|
| `tenant_id` | `[a-z][a-z0-9_]{2,30}` | `acme01` |
| Dataset BigQuery | `t_<tenant_id>_<layer>` | `t_acme01_core` |
| Dataset kiểm tra sức khỏe | `hc_<check_id>_<layer>` | `hc_01jb8x_raw` |
| Bảng raw | `<source>__<object>` | `shopee__orders` |
| Model dbt | theo spec 02 mục 2 | `stg_shopee__orders` |
| Chỉ số | `snake_case` tiếng Anh | `net_profit_after_fees` |
| Sự kiện | `<domain>.<verb_past>` | `transform.finished` |
| ID trong Postgres | ULID dạng chuỗi 26 ký tự | `01JB8X…` |
| Endpoint | `/v1/<resource>` số nhiều, kebab-case | `/v1/inputs/product-costs` |

### 3.2 Thời gian

- Lưu trữ: mọi timestamp ở UTC (`TIMESTAMP` trong BigQuery, `timestamptz` trong Postgres).
- Ngày nghiệp vụ (`date`, `order_date`, `cost_date`): tính theo giờ `Asia/Ho_Chi_Minh`.
- Tuần: tuần ISO, bắt đầu thứ Hai, theo giờ Việt Nam.
- API trả timestamp dạng ISO 8601 có offset `Z`. Giao diện hiển thị theo giờ Việt Nam.

### 3.3 Tiền

- Kho dữ liệu: `NUMERIC` (BigQuery), giữ `amount_original` + `currency` + `amount_vnd`.
- Postgres: `numeric(18,2)`.
- API: số tiền VND trả dạng số nguyên (làm tròn đến đồng); tiền nguyên tệ trả dạng chuỗi thập phân.
- Hiển thị: `1.234.567 ₫`. Tiền nguyên tệ: `$1,234.56`.

### 3.4 Lỗi và log

- API trả lỗi theo RFC 9457 (`application/problem+json`) với `type`, `title`, `detail`, `code` (mã ổn định, ví dụ `TENANT_FORBIDDEN`).
- Không ghi vào log: token, khóa API, số điện thoại, email người mua, nội dung file khách tải lên.
- Mọi request có `X-Request-Id`; nếu client không gửi thì API tạo.

### 3.5 Bảo mật mặc định

- Không có endpoint nào lấy `tenant_id` từ tham số mà không đối chiếu với quyền của người gọi trong Postgres (spec 05 mục 3).
- Không commit bí mật. `.secrets/` và `.env` nằm trong `.gitignore`. CI chạy `gitleaks`.
- Mọi service chỉ đọc cấu hình từ biến môi trường và không ghi file cục bộ ngoài thư mục tạm, để chạy được trên Cloud Run ở giai đoạn 2.

## 4. Môi trường

| Môi trường | Kho dữ liệu | Postgres | Auth | Dùng cho |
|---|---|---|---|---|
| `local` | DuckDB file `./.local/dx.duckdb` | Container | Firebase Auth Emulator | Phát triển, chạy test |
| `dev` | BigQuery project `dataxland-dev` | Container trên VM dev hoặc máy cá nhân | Firebase project `dataxland-dev` | Kiểm thử tích hợp với BigQuery thật và dữ liệu mẫu |
| `prod` | BigQuery project `dataxland-prod`, region `asia-southeast1` | Container trên VM prod | Firebase project `dataxland-prod` | Khách thật |

Biến `DX_ENV` nhận một trong ba giá trị trên. Code không được rẽ nhánh theo `DX_ENV` ngoài việc chọn adapter (DuckDB/BigQuery, emulator/thật).

### 4.1 Biến môi trường

`.env.example` liệt kê đủ các biến sau, kèm giá trị mẫu cho `local`.

| Biến | Dùng bởi | Ghi chú |
|---|---|---|
| `DX_ENV` | Tất cả | `local` \| `dev` \| `prod` |
| `DX_PUBLIC_BASE_URL` | api, web, bot | URL công khai của cổng, ví dụ `https://app.dataxland.vn` |
| `DATABASE_URL` | api, pipelines, bot | Postgres control plane |
| `GCP_PROJECT_ID` | api, pipelines | |
| `BQ_LOCATION` | pipelines | `asia-southeast1` |
| `DUCKDB_PATH` | pipelines (local) | |
| `METADATA_BUCKET` | pipelines, api | `gs://dx-meta-<env>`; local dùng `./.local/meta` |
| `FIREBASE_PROJECT_ID` | api, web | |
| `FIREBASE_AUTH_EMULATOR_HOST` | api, web (local) | |
| `CUBE_API_URL` | api | URL nội bộ của Cube |
| `CUBE_API_SECRET` | api, cube | Khóa ký JWT giữa api và Cube |
| `CUBEJS_DB_TYPE` | cube | `bigquery` hoặc `duckdb` |
| `INTERNAL_API_TOKEN` | pipelines, bot | Token cho các lời gọi nội bộ tới api |
| `TELEGRAM_BOT_TOKEN` | bot, api | Lấy từ secret |
| `TELEGRAM_WEBHOOK_SECRET` | bot | Kiểm tra header `X-Telegram-Bot-Api-Secret-Token` |
| `TELEGRAM_TEAM_CHAT_ID` | api | Nhóm Telegram nội bộ của team |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` | api | Dịch vụ email giao dịch qua SMTP |
| `WINDSOR_API_KEY` | pipelines | Chỉ để kiểm tra trạng thái, không để nạp dữ liệu |
| `FX_VCB_URL` | pipelines | Nguồn tỷ giá Vietcombank (spec 01 mục 6) |
| `ANTHROPIC_API_KEY` | api, mcp (GĐ2) | |

## 5. Khách giả lập và dữ liệu mẫu

Hai khách giả lập dùng cho mọi kiểm thử. Không bao giờ dùng dữ liệu khách thật trong test hay fixture.

| `tenant_id` | Gói | Nguồn |
|---|---|---|
| `demo_seller` | `seller` | `shopee`, `tiktok_shop`, `lazada`, `meta_ads`, `portal` |
| `demo_agency` | `agency` | `meta_ads`, `tiktok_ads`, `google_ads`, `amazon_ads`, `amazon_seller`, `shopee`, `portal` |

- File cấu hình: `tenants/demo_seller.yml`, `tenants/demo_agency.yml`.
- Dữ liệu mẫu raw: `transform/samples/<source>/<object>.jsonl`, đúng cấu trúc bảng raw (spec 01). Mỗi nguồn có ít nhất 60 ngày, 200 đơn, có đơn hủy, đơn hoàn, đơn đổi trạng thái sau khi giao, một SKU lỗ sau phí, một SKU chưa có giá vốn.
- Script `make seed-local` nạp dữ liệu mẫu vào DuckDB theo đúng dataset của từng khách giả lập, và nạp giá vốn, ngân sách mẫu vào Postgres.
- Dữ liệu mẫu được sinh bằng `ops/gen_samples.py` với seed cố định để kết quả test ổn định.

## 6. Makefile

| Lệnh | Việc |
|---|---|
| `make setup` | Cài `uv sync`, `pnpm install`, `dbt deps`, tạo `.env` từ `.env.example` nếu chưa có |
| `make up` / `make down` | Bật/tắt docker compose cho `local` |
| `make seed-local` | Nạp dữ liệu mẫu (mục 5) |
| `make dbt-build TENANT=demo_seller` | Chạy `dbt build` cho một khách |
| `make semantic` | Chạy `semantic/build.py` |
| `make test` | Toàn bộ test Python, dbt trên DuckDB, test web |
| `make lint` | ruff, mypy, sqlfluff, eslint, prettier --check |
| `make e2e` | Playwright trên stack local |

## 7. Docker Compose (local và giai đoạn 1)

`infra/compose/docker-compose.yml` gồm các service:

| Service | Image hoặc build | Cổng | Ghi chú |
|---|---|---|---|
| `postgres` | `postgres:16` | 5432 | Volume `pgdata`; database `dx` (control plane) và `dagster` |
| `api` | build `services/api` | 8000 | |
| `api-worker` | cùng image `api`, lệnh `python -m app.workers` | | Trung tâm thông báo, gửi báo cáo (spec 04 mục 5) |
| `web` | build `apps/web` | 3000 | |
| `bot` | build `services/telegram_bot` | 8100 | |
| `cube` | `cubejs/cube` | 4000 | Mount `cube/` và `semantic/cube/` |
| `dagster-webserver` | build `pipelines` | 3001 | |
| `dagster-daemon` | build `pipelines` | | |
| `metabase` | `metabase/metabase` | 3002 | Chỉ nội bộ, chỉ đọc qua SQL API của Cube |
| `caddy` | `caddy` | 80, 443 | Chỉ ở `dev` và `prod`; TLS tự động; định tuyến `app.` → web, `api.` → api, `bot.` → bot |
| `firebase-emulator` | build nhỏ từ `firebase-tools` | 9099 | Chỉ ở `local` |

Ở `prod`, Dagster UI, Metabase và Cube chỉ truy cập qua Caddy với xác thực cơ bản, hoặc qua SSH tunnel. Không mở công khai.

## 8. CI và triển khai

### 8.1 CI (GitHub Actions, mọi pull request)

1. `make lint`
2. Test Python (`pytest`), có kiểm thử tách biệt khách (mục 9)
3. `dbt build` trên DuckDB cho `demo_seller` và `demo_agency`
4. `make semantic` và kiểm tra `git diff --exit-code semantic/cube semantic/dist` (model sinh ra phải khớp YAML)
5. Kiểm tra phiên bản chỉ số (spec 03 mục 3.3)
6. Test web (`vitest`) và build Next.js
7. `gitleaks`
8. Khi có thay đổi ở `semantic/` hoặc `ai/` (GĐ2): bộ đánh giá AI

### 8.2 Triển khai giai đoạn 1

- Merge vào `main` → build image, đẩy lên Artifact Registry với tag là SHA commit.
- Job triển khai SSH vào VM prod: `git pull` (để có `tenants/` mới nhất), `docker compose pull`, `docker compose up -d`, chạy `alembic upgrade head`, chạy `ops/sync_tenants.py`.
- Triển khai lên prod yêu cầu bấm duyệt thủ công trong GitHub Environments.

### 8.3 Sao lưu

- `pg_dump` hằng ngày lúc 02:00 giờ Việt Nam lên `gs://dx-backup-prod/postgres/`, giữ 30 ngày.
- Mỗi tháng chạy thử khôi phục vào một database tạm và ghi kết quả vào `ops/runbooks/restore-log.md` (NFR-06).

## 9. Kiểm thử tách biệt khách (NFR-01)

Bắt buộc trong CI, nằm ở `services/api/tests/test_isolation.py` và `transform/tests/`.

1. Người dùng của `demo_seller` gọi mọi endpoint có dữ liệu với `X-Tenant-Id: demo_agency` → nhận `403 TENANT_FORBIDDEN`.
2. JWT Cube cho `demo_seller` truy vấn → chỉ đọc từ `t_demo_seller_marts`; kiểm tra bằng cách so SQL Cube sinh ra.
3. Không model dbt nào tham chiếu dataset của khách khác: test quét `manifest.json` sau `dbt build`.
4. Telegram: chat đã liên kết với `demo_seller` gửi `/week` không bao giờ nhận số của `demo_agency`.

## 10. Định nghĩa hoàn thành (áp dụng cho mọi spec)

Một phần việc chỉ được coi là xong khi:

- Đạt toàn bộ "Tiêu chí hoàn thành" của spec tương ứng.
- Có test tự động cho mọi tiêu chí nghiệm thu của các FR liên quan; tên test ghi mã FR, ví dụ `test_fr_ing_07_status_change_after_delivery`.
- CI xanh.
- Không còn `TODO` không có mã issue.
- Tài liệu liên quan (spec, runbook) được cập nhật nếu hành vi thay đổi.

## 11. Tiêu chí hoàn thành của spec này

- `make setup && make up && make seed-local && make test` chạy thành công trên máy mới.
- CI chạy đủ các bước ở mục 8.1 trên một PR rỗng.
- `.env.example` có đủ biến ở mục 4.1.
- Hai khách giả lập và dữ liệu mẫu tồn tại, sinh lại được bằng `ops/gen_samples.py` với kết quả giống hệt.
