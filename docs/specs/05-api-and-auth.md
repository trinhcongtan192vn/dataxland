# Spec 05 – API, dữ liệu control plane và phân quyền

Hệ thống: S6 (backend), S4 (API vận hành). Yêu cầu: FR-AUTH-01..05, FR-INP-01..05, NFR-01, NFR-02, NFR-10.

Phạm vi: dịch vụ `services/api` (FastAPI), schema Postgres, xác thực, phân quyền, danh mục endpoint. Bộ máy chỉ số ở spec 03, trung tâm thông báo ở spec 04, báo cáo và nhật ký quyết định ở spec 06, bot ở spec 08.

---

## 1. Cấu trúc dịch vụ

```
services/api/
  pyproject.toml
  alembic/
  app/
    main.py                 # tạo app, middleware request id, lỗi RFC 9457
    auth/
      firebase.py           # xác minh ID token
      context.py            # AuthContext, dependency get_ctx()
      permissions.py        # ma trận quyền (mục 4)
      internal.py           # xác thực dịch vụ nội bộ
    db/models.py            # SQLAlchemy
    routers/
      me.py tenants.py metrics.py inputs.py reports.py decisions.py
      telegram.py connect.py health_checks.py partner.py ops.py internal.py ask.py
    metrics/                # spec 03
    notify/                 # spec 04
    reports/                # spec 06
    inputs/                 # đọc, kiểm tra file Excel
    workers.py              # worker nền: notify, report sender
  tests/
```

- Chạy bằng `uvicorn`, 2 worker ở giai đoạn 1. Worker nền chạy trong tiến trình riêng `python -m app.workers` (service compose `api-worker`, dùng chung image).
- Mọi router trừ `/v1/internal/*`, `/v1/telegram/links` (POST), `/r/*`, `/v1/health-checks` (POST công khai) và `/healthz` yêu cầu người dùng đã đăng nhập.

## 2. Schema Postgres

Alembic quản lý. ID là ULID dạng chuỗi trừ khi ghi khác. Mọi bảng có `created_at`, `updated_at` (`timestamptz`).

### 2.1 Danh tính và quyền

| Bảng | Cột chính | Ghi chú |
|---|---|---|
| `tenants` | `tenant_id` (PK), `name`, `status`, `pack`, `config` jsonb, `config_hash`, `bootstrap_required`, `synced_at` | Ghi bởi `sync_tenants` (spec 04) |
| `users` | `id`, `firebase_uid` (unique), `email`, `display_name`, `staff_role` (`data_lead` \| `engineer` \| null), `disabled` | |
| `memberships` | `id`, `user_id`, `tenant_id`, `role` (`owner` \| `member`), `metric_allowlist` (text[] \| null), `invited_by` | Unique (`user_id`, `tenant_id`). `metric_allowlist = null` với owner; với member là danh sách chỉ số được xem |
| `invitations` | `id`, `tenant_id`, `email`, `role`, `metric_allowlist`, `token_hash`, `expires_at`, `accepted_at`, `revoked_at` | Hết hạn sau 7 ngày |
| `partners` | `partner_id` (PK), `name`, `contact_email` | Đồng bộ từ `tenants/partners.yml` |
| `partner_users` | `user_id`, `partner_id` | Người của agency |
| `partner_grants` | `id`, `tenant_id`, `partner_id`, `granted_by`, `granted_at`, `revoked_at`, `revoked_by` | Quyền đang hiệu lực: `revoked_at is null` |
| `audit_log` | `id`, `actor_user_id`, `actor_service`, `tenant_id`, `action`, `target`, `detail` jsonb, `at` | Mục 7 |

### 2.2 Nhập liệu

| Bảng | Cột chính | Ràng buộc |
|---|---|---|
| `product_costs` | `id`, `tenant_id`, `seller_sku`, `unit_cost_vnd` numeric(18,2), `valid_from` date, `note`, `created_by`, `deleted_at` | Unique (`tenant_id`, `seller_sku`, `valid_from`) với bản ghi chưa xóa; `unit_cost_vnd >= 0` |
| `ad_budgets` | `id`, `tenant_id`, `platform`, `month` date (ngày 1), `budget_vnd` numeric(18,2), `created_by`, `deleted_at` | Unique (`tenant_id`, `platform`, `month`) với bản ghi chưa xóa; `platform` thuộc nguồn quảng cáo của khách |
| `upload_jobs` | `id`, `tenant_id`, `kind`, `filename`, `rows_total`, `rows_ok`, `rows_error`, `errors` jsonb, `created_by` | Không lưu nội dung file |

### 2.3 Các bảng của spec khác

| Bảng | Spec |
|---|---|
| `events`, `event_offsets`, `event_processed`, `event_dead_letters` | 04 mục 4 |
| `notifications` | 04 mục 5.4 |
| `pipeline_runs`, `source_syncs` | 04 mục 6 |
| `erasure_log` | 04 mục 8 |
| `metric_queries` | 03 mục 4.2 |
| `reports`, `report_recipients`, `report_opens` | 06 mục 4 |
| `decisions` | 06 mục 7 |
| `telegram_link_codes`, `telegram_links`, `telegram_rate` | 08 mục 3 |
| `health_checks`, `health_check_files` | 07 mục 3 |
| `oauth_states` | Mục 6.7 |
| `fx_manual_rates` | Mục 6.9 |
| `metric_requests`, `ask_logs` (GĐ2) | 09 |

## 3. Xác thực

### 3.1 Người dùng (FR-AUTH-01)

- Client gửi `Authorization: Bearer <Firebase ID token>`.
- API xác minh bằng `firebase-admin` (`verify_id_token`, `check_revoked=True`). Ở `local` dùng Firebase Auth Emulator.
- Lần đầu gặp `firebase_uid`: tạo `users`. Nếu email có lời mời chưa hết hạn, tạo `memberships` tương ứng.
- Phương thức đăng nhập: email + mật khẩu (có xác minh email) và Google.

### 3.2 Chọn khách và quyền (NFR-01, FR-AUTH-04)

Dependency `get_ctx()` tạo `AuthContext` cho mỗi request:

1. Xác định người dùng từ token.
2. Đọc header `X-Tenant-Id`. Nếu không có và người dùng chỉ thuộc đúng một khách (qua `memberships` hoặc `partner_grants` đang hiệu lực), dùng khách đó; nếu không, trả `400 TENANT_REQUIRED`.
3. Tính vai trò hiệu lực với khách đó, **đọc từ Postgres ở mỗi request, không dùng cache**:
   - `memberships.role` nếu có;
   - `partner` nếu người dùng thuộc một `partner_id` có `partner_grants` đang hiệu lực với khách;
   - `data_lead` hoặc `engineer` nếu `users.staff_role` có giá trị (nhân viên DataxLand xem được mọi khách).
   - Không có vai trò nào → `403 TENANT_FORBIDDEN`.
4. `AuthContext`: `user_id`, `tenant_id`, `role`, `metric_scope` (`all` hoặc danh sách), `pack`, `dataset_prefix`.

Vì quyền được đọc lại ở mỗi request, thu quyền có hiệu lực ngay ở lần gọi kế tiếp.

**Custom claims.** API đặt claims `{role_hint, tenant_ids, partner_id}` khi quyền đổi, chỉ để giao diện hiển thị menu phù hợp. Không đoạn code backend nào dùng claims để quyết định quyền.

### 3.3 Dịch vụ nội bộ

- `Authorization: Bearer <INTERNAL_API_TOKEN>` kèm `X-Service: dagster | bot | ops`.
- Chỉ vào được `/v1/internal/*`, `POST /v1/telegram/links` và các endpoint mà bot gọi thay người dùng (mục 3.4).
- Endpoint nội bộ không mở qua Caddy ra Internet: Caddy chặn đường dẫn `/v1/internal/` từ bên ngoài.

### 3.4 Bot gọi thay người dùng

Bot gửi token nội bộ kèm `X-Telegram-Chat-Id`. API:

1. Tìm `telegram_links` đang hoạt động cho chat đó. Không có → `403 TELEGRAM_NOT_LINKED`.
2. Với chat riêng: dựng `AuthContext` như mục 3.2 cho `user_id` của liên kết và `tenant_id` của liên kết. Người dùng mất quyền với khách → gỡ liên kết, phát `telegram.unlinked`, trả `403 TELEGRAM_NOT_LINKED`.
3. Với nhóm: vai trò là `group`, `metric_scope` là phạm vi owner đã chọn. Kiểm tra owner đã liên kết nhóm vẫn còn là owner; nếu không, gỡ liên kết.

## 4. Ma trận quyền (FR-AUTH-02)

`permissions.py` định nghĩa quyền theo hành động; router gọi `require(ctx, "<action>")`.

| Hành động | owner | member | partner | data_lead | engineer | group (Telegram) |
|---|---|---|---|---|---|---|
| `metrics.read` | ✓ | ✓ theo danh sách | ✓ chỉ số agency và chung | ✓ | ✓ | ✓ theo phạm vi |
| `reports.read` | ✓ | ✓ | ✓ (gói agency) | ✓ | ✓ | ✓ tin tóm tắt |
| `reports.edit`, `reports.approve` | | | | ✓ | | |
| `inputs.read` | ✓ | ✓ | ✓ ngân sách | ✓ | ✓ | |
| `inputs.write` | ✓ | | ✓ ngân sách | ✓ | | |
| `decisions.read` | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `decisions.write` | ✓ | | ✓ | ✓ | | |
| `users.manage` | ✓ | | | ✓ | | |
| `partners.manage` | ✓ | | | | | |
| `telegram.link_self` | ✓ | ✓ | ✓ | ✓ | ✓ | |
| `telegram.link_group`, `telegram.manage` | ✓ | | | | | |
| `connect.sources` | | | | ✓ | | |
| `ops.read` | | | | ✓ | ✓ | |
| `ops.write` (FX tay, chạy lại) | | | | ✓ | | |
| `healthchecks.review` | | | | ✓ | | |

Test `test_fr_auth_02_permission_matrix` chạy mọi ô của bảng này với khách giả lập.

## 5. Người dùng và chia sẻ

### 5.1 Mời và gỡ member (FR-AUTH-03)

| Method | Đường dẫn | Việc |
|---|---|---|
| `GET` | `/v1/members` | Danh sách thành viên và lời mời của khách |
| `POST` | `/v1/members/invitations` | `{email, role: member, metric_allowlist}` → gửi email mời có link `DX_PUBLIC_BASE_URL/invite/<token>` |
| `DELETE` | `/v1/members/invitations/{id}` | Hủy lời mời |
| `PUT` | `/v1/members/{user_id}` | Đổi `metric_allowlist` |
| `DELETE` | `/v1/members/{user_id}` | Gỡ member; gỡ luôn liên kết Telegram của người đó với khách này |

- Owner không gỡ được chính mình nếu là owner duy nhất (`409 LAST_OWNER`).
- `metric_allowlist` chỉ nhận chỉ số không ẩn của gói khách.

### 5.2 Ẩn thông tin cá nhân người mua (FR-AUTH-05)

- Không bảng nào trong Postgres và không mart nào chứa thông tin cá nhân người mua dạng gốc, nên API không có nguồn để trả.
- Test `test_fr_auth_05_no_buyer_pii_in_responses`: quét mọi response model trong OpenAPI, không có trường tên chứa `phone`, `address`, `buyer_name`, `buyer_email`; và chạy mọi endpoint GET với dữ liệu mẫu, kiểm tra không có chuỗi giống số điện thoại Việt Nam.

### 5.3 Cấp quyền cho agency (FR-AUTH-04)

| Method | Đường dẫn | Việc |
|---|---|---|
| `GET` | `/v1/partners/grants` | Agency đang có quyền với khách này |
| `POST` | `/v1/partners/grants` | `{partner_id}`: cấp quyền |
| `DELETE` | `/v1/partners/grants/{id}` | Thu quyền: đặt `revoked_at`; gỡ liên kết Telegram của người dùng agency với khách |

Chỉ owner gọi được. Mỗi thay đổi ghi `audit_log`.

## 6. Danh mục endpoint

Lỗi theo spec 00 mục 3.4. Danh sách phân trang dùng `?cursor=&limit=` (mặc định 50, tối đa 200), trả `{items, next_cursor}`.

### 6.1 Bản thân và khách

| Method | Đường dẫn | Mô tả |
|---|---|---|
| `GET` | `/v1/me` | Người dùng, danh sách khách và vai trò, `partner_id`, `staff_role` |
| `GET` | `/v1/tenants/{id}` | Cấu hình đã đồng bộ, bỏ `secret_ref`. Người gọi phải có vai trò với khách đó |

### 6.2 Chỉ số

Theo spec 03: `POST /v1/metrics/query`, `GET /v1/metrics`, `GET /v1/metrics/key-numbers`, `GET /v1/metrics/flags`.

### 6.3 Giá vốn (FR-INP-01..03)

| Method | Đường dẫn | Mô tả |
|---|---|---|
| `GET` | `/v1/inputs/product-costs` | Lọc `?sku=&active_on=YYYY-MM-DD`. Mỗi dòng có `seller_sku`, `unit_cost_vnd`, `valid_from`, `valid_to` (tính) |
| `POST` | `/v1/inputs/product-costs` | `{seller_sku, unit_cost_vnd, valid_from, note?}` |
| `PUT` | `/v1/inputs/product-costs/{id}` | Sửa `unit_cost_vnd`, `note`. Đổi `valid_from` thì tạo bản mới |
| `DELETE` | `/v1/inputs/product-costs/{id}` | Xóa mềm |
| `GET` | `/v1/inputs/product-costs/template` | File Excel mẫu (mục 6.4) |
| `POST` | `/v1/inputs/product-costs/upload` | `multipart/form-data`, file `.xlsx` hoặc `.csv` |
| `GET` | `/v1/inputs/product-costs/missing` | SKU có doanh thu 30 ngày mà chưa có giá vốn, kèm doanh thu; đọc qua bộ máy chỉ số (mart `mrt_seller__order_lines` với `has_missing_cogs`) |

Mỗi thay đổi phát `inputs.changed` (`kind: product_costs`). Dagster chạy lại pipeline sau 10 phút không có thay đổi mới (spec 04 mục 3.5).

### 6.4 File Excel giá vốn (FR-INP-02)

Mẫu có một sheet `gia_von`, dòng 1 là tiêu đề:

| Cột | Bắt buộc | Định dạng |
|---|---|---|
| `ma_sku` | có | Chuỗi, trùng `seller_sku` trên sàn |
| `gia_von` | có | Số, VND, ≥ 0; chấp nhận `120000`, `120.000`, `120,000` |
| `ap_dung_tu` | có | `dd/mm/yyyy` hoặc ô kiểu ngày |
| `ghi_chu` | không | |

Sheet thứ hai `huong_dan` giải thích bằng tiếng Việt. Mẫu có sẵn danh sách SKU đang bán của khách (lấy từ `dim_product` qua bộ máy chỉ số) để khách chỉ cần điền giá.

Xử lý:

- Tối đa 5.000 dòng, 2 MB. Đọc bằng `openpyxl` ở chế độ chỉ đọc, bỏ công thức, chỉ lấy giá trị.
- Kiểm từng dòng; dòng hợp lệ được upsert theo (`seller_sku`, `ap_dung_tu`), dòng lỗi không làm hỏng dòng khác.
- Response: `{upload_id, rows_total, rows_ok, rows_error, errors: [{row, column, code, message_vi}]}`. Mã lỗi: `REQUIRED`, `INVALID_NUMBER`, `NEGATIVE`, `INVALID_DATE`, `DUPLICATE_IN_FILE`, `UNKNOWN_SKU` (chỉ là cảnh báo, dòng vẫn được nhận).
- Ghi `upload_jobs`; không lưu file.

### 6.5 Ngân sách quảng cáo (FR-INP-04)

| Method | Đường dẫn | Mô tả |
|---|---|---|
| `GET` | `/v1/inputs/ad-budgets` | `?from_month=&to_month=` |
| `POST` | `/v1/inputs/ad-budgets` | `{platform, month: "2026-10", budget_vnd}` |
| `PUT` | `/v1/inputs/ad-budgets/{id}` | Sửa `budget_vnd` |
| `DELETE` | `/v1/inputs/ad-budgets/{id}` | Xóa mềm |

`platform` phải là nguồn quảng cáo khách có. Phát `inputs.changed` (`kind: ad_budgets`).

FR-INP-05 (ngân sách theo chiến dịch, giai đoạn 2): thêm cột `campaign_id` nullable và mở rộng `dim_ad_budget`; chưa làm ở giai đoạn 1.

### 6.6 Báo cáo, nhật ký quyết định, agency

Đặc tả ở spec 06: `/v1/reports*`, `/r/{token}`, `/v1/decisions*`, `/v1/partner/tenants`.

### 6.7 Kết nối sàn (OAuth)

| Method | Đường dẫn | Mô tả |
|---|---|---|
| `POST` | `/v1/connect/{source}/start` | `source` ∈ `shopee`, `tiktok_shop`, `lazada`. Tạo `oauth_states` (`state` ngẫu nhiên, `tenant_id`, `user_id`, hết hạn 15 phút), trả `{authorize_url}` |
| `GET` | `/v1/connect/{source}/callback` | Kiểm tra `state` (dùng một lần); đổi mã lấy token; ghi secret `dx-<tenant_id>-<source>-<account_id>`; cập nhật `source_syncs`; chuyển hướng về `/ops/tenants/<id>?connected=<source>` |

Chỉ `data_lead`. Không token nào được trả về trình duyệt hay ghi log.

### 6.8 Telegram

| Method | Đường dẫn | Gọi bởi | Mô tả |
|---|---|---|---|
| `POST` | `/v1/telegram/link-codes` | Người dùng | Tạo mã, body `{kind: private \| group, metric_scope?}`. Spec 08 mục 3 |
| `GET` | `/v1/telegram/links` | Người dùng | Liên kết của tôi; owner thấy mọi liên kết của khách |
| `DELETE` | `/v1/telegram/links/{id}` | Người dùng | Gỡ liên kết của mình; owner gỡ mọi liên kết của khách |
| `POST` | `/v1/telegram/links` | Bot | Đổi mã lấy liên kết |
| `POST` | `/v1/telegram/unlink` | Bot | `/unlink` trong chat |
| `POST` | `/v1/telegram/chat-left` | Bot | Bot bị xóa khỏi nhóm hoặc bị chặn |
| `GET` | `/v1/telegram/context` | Bot | Các khách chat này đã liên kết |
| `POST` | `/v1/telegram/messages/{kind}` | Bot | Dựng tin trả lời lệnh từ mẫu chung (spec 08 mục 2) |

### 6.9 Vận hành

| Method | Đường dẫn | Quyền | Mô tả |
|---|---|---|---|
| `GET` | `/v1/ops/overview` | `ops.read` | Một dòng mỗi khách: nguồn và lần đồng bộ, test lỗi, trạng thái báo cáo tuần, mở báo cáo (spec 04 mục 6) |
| `GET` | `/v1/ops/tenants/{id}/runs` | `ops.read` | Lịch sử chạy, bước lỗi, lỗi chặn |
| `POST` | `/v1/ops/tenants/{id}/runs` | `ops.write` | Yêu cầu chạy lại `tenant_pipeline` (phát sự kiện nội bộ cho Dagster) |
| `POST` | `/v1/admin/fx-rates` | `ops.write` | Nhập tỷ giá tay `{date, currency, rate_vnd}` vào `fx_manual_rates`; connector `fx_vcb` ghép bảng này vào `dx_ref.fx_rates` với `source = manual` |

### 6.10 Nội bộ

| Method | Đường dẫn | Gọi bởi | Mô tả |
|---|---|---|---|
| `GET` | `/v1/internal/tenants` | Dagster, Cube | Danh sách khách theo `status` |
| `POST` | `/v1/internal/runs` | Dagster | Ghi trạng thái lần chạy và nguồn |
| `POST` | `/v1/internal/anomalies/run` | Dagster | Spec 03 mục 8 |
| `POST` | `/v1/internal/reports/build` | Dagster | Dựng báo cáo tuần (spec 06 mục 4) |
| `POST` | `/v1/events` | Dịch vụ nội bộ | Phát sự kiện |

### 6.11 Kiểm tra sức khỏe, AI

`/v1/health-checks*` ở spec 07; `POST /v1/ask` ở spec 09 (giai đoạn 2).

## 7. Nhật ký kiểm toán (NFR-10, NFR-11)

Ghi `audit_log` cho: đăng nhập lần đầu, mời và gỡ thành viên, đổi danh sách chỉ số, cấp và thu quyền agency, liên kết và gỡ Telegram, nhập và sửa giá vốn, ngân sách, tải file, duyệt và gửi báo cáo, kết nối sàn, nhập tỷ giá tay, xóa dữ liệu người mua. Giữ tối thiểu 2 năm.

## 8. Giới hạn tần suất

- Theo người dùng: 120 request mỗi phút cho mọi endpoint, 30 mỗi phút cho `POST /v1/metrics/query`. Vượt → `429 RATE_LIMITED` với `Retry-After`.
- Cài bằng bộ đếm cửa sổ trượt trong Postgres ở giai đoạn 1 (bảng `rate_counters`), đổi sang Redis hoặc Memorystore nếu cần ở giai đoạn 2.
- `POST /v1/health-checks`: 5 lượt mỗi email mỗi ngày, 20 mỗi IP mỗi ngày.

## 9. Kiểm thử

| Test | Nội dung | FR |
|---|---|---|
| `test_isolation.py` | 4 trường hợp ở spec 00 mục 9 | NFR-01 |
| `test_fr_auth_01_firebase_token` | Token hợp lệ qua; token sai, hết hạn, bị thu hồi → 401 | FR-AUTH-01 |
| `test_fr_auth_02_permission_matrix` | Mọi ô mục 4 | FR-AUTH-02 |
| `test_fr_auth_03_member_allowlist` | Member gọi chỉ số ngoài danh sách → `403 METRIC_FORBIDDEN` | FR-AUTH-03 |
| `test_fr_auth_04_revoke_is_immediate` | Thu quyền agency, request kế tiếp → 403; liên kết Telegram của agency bị gỡ | FR-AUTH-04 |
| `test_fr_auth_05_no_buyer_pii_in_responses` | Mục 5.2 | FR-AUTH-05 |
| `test_fr_inp_01_cost_effective_date` | Giá vốn mới từ ngày X chỉ ảnh hưởng đơn từ X (chạy cùng dbt trên DuckDB) | FR-INP-01 |
| `test_fr_inp_02_excel_partial_accept` | File có 3 dòng lỗi và 7 dòng đúng: nhận 7, báo đúng dòng và lý do | FR-INP-02 |
| `test_fr_inp_04_budget_platform_validation` | Nền tảng khách không có → 400 | FR-INP-04 |
| `test_internal_endpoints_reject_user_token` | Token người dùng gọi `/v1/internal/*` → 403 | NFR-02 |
| `test_oauth_state_single_use` | `state` dùng lần hai → 400 | |

## 10. Tiêu chí hoàn thành

- `alembic upgrade head` tạo đủ bảng ở mục 2 trên Postgres trống.
- OpenAPI sinh tại `/openapi.json`; `apps/web` sinh client TypeScript từ file này (`pnpm gen:api`).
- Đăng nhập bằng emulator, chọn khách, gọi được chỉ số và nhập liệu với hai khách giả lập.
- Mọi test ở mục 9 qua.
