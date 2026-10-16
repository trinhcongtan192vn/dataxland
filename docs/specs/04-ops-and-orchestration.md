# Spec 04 – Vận hành và điều phối

Hệ thống: S4. Yêu cầu: FR-OPS-01..09, FR-ING-06, FR-DQ-04, FR-REP-01 (lịch dựng), NFR-05, NFR-08, NFR-12.

Phạm vi: sổ đăng ký khách, script tạo khách, sự kiện, Dagster, trung tâm thông báo, dữ liệu cho màn hình vận hành, xóa dữ liệu người mua. Giao diện màn hình vận hành ở spec 06; endpoint ở spec 05.

---

## 1. Sổ đăng ký khách (FR-OPS-01)

### 1.1 Schema `tenants/<tenant_id>.yml`

Model Pydantic `dx_common.tenants.TenantConfig`. Trường không ghi thì lấy mặc định theo gói.

```yaml
tenant_id: demo_seller          # bắt buộc, trùng tên file
name: Shop Demo                 # bắt buộc
status: active                  # trial | active | paused | offboarding
pack: seller                    # seller | agency
warehouse:
  provider: bigquery            # bigquery | duckdb (chỉ local)
  project: dataxland-prod
  location: asia-southeast1
sources:
  - type: shopee                # tên nguồn, trùng tiền tố bảng raw
    connector: dlt              # dlt | windsor
    account_id: "123456"        # shop_id hoặc mã tài khoản quảng cáo
    secret_ref: dx-demo_seller-shopee-123456   # chỉ với dlt
    enabled: true
  - type: meta_ads
    connector: windsor
    account_id: "act_987"
  - type: portal                # luôn có, bootstrap tự thêm nếu thiếu
    connector: dlt
schedule:
  sync: "0 */6 * * *"           # cron, giờ Việt Nam
  weekly_report: "MON 07:00"
quality:
  freshness_hours: 8
  reconcile_tolerance_pct: {default: 1.0}
  provisional_window_days: {default: 14}
cost_allocation: by_revenue     # by_revenue | by_order | none
attention:                      # chỉ dùng với gói agency
  overspend_pct: 15
  roas_drop_pct: 25
  platform_gap_pct: 50
features:
  identity: false
identity:                       # GĐ2, spec 10
  suggest_threshold: 0.7
overrides:
  status_map: tenants/overrides/demo_seller_status_map.csv
notify:
  channels: [telegram, email]
  email: [owner@example.com]
  anomaly_alerts: true
benchmark_opt_in: false
partners: []                    # partner_id được xem khách này
```

Mặc định theo gói:

| Trường | `seller` | `agency` |
|---|---|---|
| `schedule.sync` | `0 */6 * * *` | `0 */3 * * *` |
| `quality.freshness_hours` | 8 | 5 |

`freshness_hours` mặc định lớn hơn chu kỳ đồng bộ để một lần chạy trễ không làm chặn báo cáo.

Quy tắc kiểm tra (`dx_common.tenants.validate`):

- `tenant_id` đúng quy ước (spec 00 mục 3.1) và trùng tên file.
- `secret_ref` bắt buộc với nguồn `connector: dlt` trừ `portal`; cấm mọi trường có tên chứa `token`, `key`, `password`, `secret` ngoài `secret_ref`.
- `reconcile_tolerance_pct` chấp nhận số (hiểu là `default`) hoặc map.
- `partners` chỉ chứa `partner_id` có trong `tenants/partners.yml`.
- `pack: agency` mà không có nguồn quảng cáo nào → lỗi.

CI chạy `python -m dx_common.tenants validate tenants/` trên mọi PR.

### 1.2 Đối tác agency

`tenants/partners.yml` liệt kê đối tác: `partner_id`, `name`, `contact_email`. Việc khách cấp quyền cho đối tác diễn ra trên cổng (spec 05 mục 5.3) và ghi vào Postgres; trường `partners` trong file khách được `sync_tenants` đối chiếu và cảnh báo nếu lệch, không ghi đè quyền trên cổng.

### 1.3 Đồng bộ vào Postgres

`ops/sync_tenants.py`:

1. Đọc và kiểm tra mọi file trong `tenants/`. File lỗi thì bỏ qua file đó, ghi lỗi và gửi thông báo cho team.
2. Upsert vào bảng `tenants` (spec 05 mục 2): `tenant_id`, `name`, `status`, `pack`, `config` (jsonb, bản đã điền mặc định), `config_hash`, `synced_at`.
3. Khách có trong Postgres nhưng không còn file: đặt `status = 'archived'`, không xóa.
4. Khách mới (chưa từng bootstrap): ghi `bootstrap_required = true` và gửi thông báo cho team.

Chạy khi:

- Triển khai (spec 00 mục 8.2).
- Dagster schedule `sync_tenants` mỗi 5 phút: `git fetch` nhánh `main` bằng deploy key chỉ đọc, chỉ lấy thư mục `tenants/`, rồi chạy script. Nhờ vậy sửa file và merge thì trong 5 phút hệ thống dùng cấu hình mới mà không cần triển khai lại.

## 2. Tạo khách (FR-OPS-02)

`ops/bootstrap_tenant.py <tenant_id> [--env dev|prod]`. Chạy lại không tạo trùng.

| Bước | Việc | Ghi chú |
|---|---|---|
| 1 | Đọc cấu hình từ Postgres | Khách phải đã được đồng bộ |
| 2 | Tạo dataset `t_<id>_raw`, `_stg`, `_core`, `_marts` ở `warehouse.location` | Nhãn `tenant_id=<id>` |
| 3 | Tạo tài khoản dịch vụ `dxt-<slug>` | `slug`: `tenant_id` đổi `_` thành `-`, cắt cho đủ 30 ký tự, thêm 4 ký tự hash nếu bị cắt |
| 4 | Cấp quyền | `dataEditor` trên 4 dataset của khách; `dataViewer` trên `dx_ref`; `jobUser` ở project. Cấp `dataViewer` trên `t_<id>_marts` cho `dx-cube` |
| 5 | Tạo secret `dx-<id>-pii-salt` | 32 byte ngẫu nhiên; không bao giờ đổi khi đã có |
| 6 | Kiểm tra mọi `secret_ref` tồn tại | Thiếu thì in danh sách cần tạo, không dừng |
| 7 | Tạo view Windsor nếu cần | Spec 01 mục 8.2 |
| 8 | Đặt `bootstrap_required = false`, phát `tenant.created` | |
| 9 | In checklist thủ công | Kết nối Windsor, cấp quyền OAuth cho sàn, liên kết Telegram cho owner |

Ở `local`, script chỉ tạo schema DuckDB và secret trong `.secrets/`.

## 3. Pipeline Dagster (FR-OPS-03)

### 3.1 Code location

```
pipelines/
  dx_pipelines/
    definitions.py
    resources.py          # dbt, BigQuery/DuckDB, dlt, api_client, secrets
    partitions.py         # dynamic partitions "tenants"
    jobs/
      tenant_pipeline.py
      weekly_report.py
      fx_daily.py
      healthcheck.py      # spec 07
      housekeeping.py     # xóa dataset kiểm tra sức khỏe hết hạn, nhắc đo lại quyết định
    sensors/
      tenant_partitions.py
      tenant_schedule.py
      events.py
  connectors/             # spec 01
```

- Partition động `tenants`: sensor `tenant_partitions` (mỗi phút) đồng bộ danh sách partition với khách `active` và `trial` trong Postgres.
- Mỗi khách chỉ một lần chạy cùng lúc (tag `dx/tenant=<id>` với giới hạn đồng thời 1). Toàn hệ thống tối đa 3 lần chạy đồng thời ở giai đoạn 1.
- Mỗi lần chạy dùng tài khoản dịch vụ của khách (impersonation), không dùng tài khoản của Dagster để đọc ghi dữ liệu khách.

### 3.2 Job `tenant_pipeline`

| Bước | Việc | Lỗi thì |
|---|---|---|
| `load_overrides` | Nạp file ghi đè trạng thái vào `<prefix>_raw.dx__status_map_override` | Dừng, `sync.failed` (`reason: override_invalid`) |
| `sync_sources` | Chạy từng connector dlt đang bật của khách, kể cả `portal` | Dừng, `sync.failed` với `source`, `reason` |
| `check_windsor_freshness` | Spec 01 mục 8.3 | Dừng, `sync.failed` (`reason: windsor_stale`) |
| `dbt_build` | `dbt source freshness` rồi `dbt build` với biến ở spec 02 mục 1.1; marts vào bảng `__staging` | Lỗi chạy (không phải lỗi test): dừng, `sync.failed` (`reason: dbt_error`) |
| `evaluate_tests` | Đọc `run_results.json` và kết quả freshness. Có test `severity: error` lỗi → chặn | Chặn: dừng, `test.failed` |
| `swap_marts` | Macro `dx_swap_marts()` | Dừng, `sync.failed` (`reason: swap_failed`) |
| `upload_run_metadata` | Đẩy `manifest.json`, `run_results.json`, `sources.json`, báo cáo Elementary lên `METADATA_BUCKET/<tenant_id>/<run_id>/` | Ghi cảnh báo, không dừng |
| `refresh_cube` | Gọi Cube build pre-aggregation cho khách | Dừng, `sync.failed` (`reason: cube_refresh_failed`) |
| `emit_finished` | Phát `transform.finished` | |
| `detect_anomalies` | `POST /v1/internal/anomalies/run` (spec 03 mục 8) | Ghi cảnh báo, không dừng |

Mỗi bước ghi trạng thái vào bảng `pipeline_runs` và `source_syncs` qua `POST /v1/internal/runs` (spec 05) để màn hình vận hành đọc.

**Khi bị chặn (FR-DQ-04).** Marts không được hoán đổi, Cube không được làm mới, không phát `transform.finished`, không dựng báo cáo. Dashboard tiếp tục đọc marts của lần chạy tốt trước. `mrt_common__data_status.data_as_of` giữ thời điểm cũ, nên cổng và bot hiện đúng thời điểm cập nhật cũ.

Payload `test.failed`:

```json
{
  "run_id": "…",
  "failures": [
    {"test": "reconcile_daily_totals_shopee", "severity": "error",
     "rows": [{"source": "shopee", "date": "2026-10-14", "metric": "gross_amount", "expected": 52000000, "actual": 50500000, "diff_pct": 2.9}]}
  ]
}
```

Tối đa 20 dòng mỗi test trong payload.

### 3.3 Lịch theo cấu hình (FR-ING-06, FR-REP-01)

Sensor `tenant_schedule` chạy mỗi phút:

- Với mỗi khách: nếu `schedule.sync` (cron theo giờ Việt Nam) có thời điểm đến hạn chưa chạy kể từ lần đánh giá trước, mở lần chạy `tenant_pipeline` với `run_key = <tenant_id>:<thời điểm đến hạn>`.
- Nếu `schedule.weekly_report` đến hạn: mở `weekly_report` cho khách (spec 06 mục 4). Job này chờ tối đa 3 giờ cho một lần `tenant_pipeline` thành công bắt đầu sau thời điểm đến hạn trừ chu kỳ đồng bộ; không có thì dựng báo cáo từ lần chạy tốt gần nhất và đánh dấu `data_stale = true`.
- Đổi cron trong file cấu hình thì lịch đổi theo ở lần đánh giá kế tiếp, không cần sửa code.

### 3.4 Job cố định

| Job | Lịch (giờ Việt Nam) | Việc |
|---|---|---|
| `fx_daily` | 18:30 hằng ngày | Spec 01 mục 6 |
| `sync_tenants` | Mỗi 5 phút | Mục 1.3 |
| `healthcheck_cleanup` | 03:00 hằng ngày | Spec 07 mục 6 |
| `decision_reminders` | 08:00 hằng ngày | Phát nhắc đo lại quyết định đến hạn (spec 06 mục 7) |
| `events_cleanup` | 04:00 hằng ngày | Xóa sự kiện đã xử lý cũ hơn 90 ngày |

### 3.5 Sensor sự kiện

Sensor `events` tiêu thụ sự kiện cho Dagster (consumer `dagster`):

| Sự kiện | Việc |
|---|---|
| `tenant.created` | Mở `tenant_pipeline` cho khách mới (nạp lịch sử, spec 01 mục 2.1) |
| `healthcheck.submitted` | Mở job `healthcheck` (spec 07) |
| `inputs.changed` | Mở `tenant_pipeline` sau 10 phút nếu không có sự kiện mới hơn, để giá vốn hoặc ngân sách vừa sửa có hiệu lực |

## 4. Sự kiện

### 4.1 Bảng outbox (giai đoạn 1)

```sql
create table events (
  event_id     text primary key,          -- ULID
  type         text not null,
  version      int  not null default 1,
  tenant_id    text,
  occurred_at  timestamptz not null,
  producer     text not null,
  payload      jsonb not null
);
create index on events (type, event_id);

create table event_offsets (
  consumer     text primary key,
  last_event_id text not null,
  updated_at   timestamptz not null
);

create table event_processed (
  consumer  text,
  event_id  text,
  processed_at timestamptz not null,
  primary key (consumer, event_id)
);
```

### 4.2 `dx_common.events`

- `publish(type, tenant_id, payload, producer)`: kiểm tra payload theo model Pydantic của loại sự kiện, ghi một dòng. Trong transaction của bên gọi nếu có.
- `consume(consumer, types, handler, batch=100)`: đọc sự kiện có `event_id > last_event_id`, gọi `handler` cho từng sự kiện chưa có trong `event_processed`, ghi `event_processed` và cập nhật offset. Lỗi handler thì dừng lô, thử lại ở lần sau (tối đa 5 lần cho một sự kiện, sau đó ghi vào `event_dead_letters` và báo team).
- Giai đoạn 2 thay phần cài đặt bằng Pub/Sub, giữ nguyên chữ ký hai hàm.

### 4.3 Danh mục sự kiện

Danh mục theo `architecture.md` mục 11.2, cộng thêm các sự kiện nội bộ dưới đây. Model payload nằm trong `dx_common/events/schemas.py`.

| Sự kiện | Payload |
|---|---|
| `tenant.created` | `{}` |
| `sync.failed` | `{run_id, source, reason, detail}` |
| `transform.finished` | `{run_id, data_as_of}` |
| `test.failed` | Mục 3.2 |
| `metric.anomaly` | Spec 03 mục 8 |
| `report.ready` | `{report_id, period}` |
| `telegram.linked`, `telegram.unlinked` | `{link_id, chat_type}` |
| `decision.logged` | `{decision_id}` |
| `decision.remeasure_due` | `{decision_id}` |
| `metric.released` | `{metric, old_version, new_version}` |
| `healthcheck.submitted` | `{check_id}` |
| `healthcheck.completed` | `{check_id}` |
| `inputs.changed` | `{kind: product_costs \| ad_budgets}` |
| `match.proposed` (GĐ2) | Spec 10 |

`reason` của `sync.failed`: `auth_revoked`, `rate_limited`, `api_error`, `windsor_stale`, `override_invalid`, `dbt_error`, `swap_failed`, `cube_refresh_failed`.

## 5. Trung tâm thông báo (FR-OPS-05, FR-OPS-08, NFR-12)

Module `services/api/app/notify/`, chạy như worker nền của API (consumer `notify`, đọc sự kiện mỗi 30 giây).

### 5.1 Giao diện kênh

```python
class Channel(Protocol):
    name: str                                    # "telegram", "email"
    def supports(self, recipient: Recipient) -> bool: ...
    async def send(self, recipient: Recipient, message: RenderedMessage) -> DeliveryResult: ...
```

- `Recipient`: `{kind: user | team | telegram_chat | email, address, tenant_id?, scope?}`.
- `RenderedMessage`: tiêu đề, thân văn bản, các nút `{label, url}`. Mỗi kênh tự đổi sang định dạng của mình.
- Adapter: `TelegramChannel` (gọi Bot API `sendMessage` với `parse_mode=HTML` và inline keyboard), `EmailChannel` (SMTP, gửi kèm bản HTML và văn bản thuần).
- Danh sách kênh đăng ký trong `notify/channels/__init__.py`. Thêm kênh mới (ví dụ Zalo) là thêm một adapter, không sửa `dispatcher.py` (FR-OPS-08).

### 5.2 Mẫu tin

```
services/api/app/notify/templates/
  report_ready/
    meta.yml            # version, audience, kênh hỗ trợ
    telegram.html.j2
    email.html.j2
    email.txt.j2
  anomaly/
  sync_failed/
  test_failed/
  decision_remeasure_due/
  healthcheck_ready/
```

- Một mẫu cho một loại tin; mọi kênh dùng cùng dữ liệu đầu vào, chỉ khác định dạng.
- `meta.yml` có `version`; mỗi lần gửi ghi lại phiên bản mẫu.
- Mẫu gửi khách không nhận được trường thông tin cá nhân người mua: dữ liệu đầu vào của mẫu chỉ gồm số tổng hợp và link.

### 5.3 Ai nhận gì

| Sự kiện | Team (nhóm Telegram nội bộ + email team) | Khách |
|---|---|---|
| `sync.failed`, `test.failed` | Có | Không |
| `metric.anomaly` | Có | Có nếu `notify.anomaly_alerts: true` và lần chạy không bị chặn |
| `report.ready` | Không | Có |
| `decision.remeasure_due` | Có | Không |
| `healthcheck.submitted`, `healthcheck.completed` | Có | Không (link gửi sau khi duyệt, spec 07) |
| `tenant.created`, cấu hình lỗi | Có | Không |

Người nhận phía khách:

- Email: `notify.email` trong cấu hình, cộng email của người dùng có vai trò `owner` của khách.
- Telegram: mọi liên kết đang hoạt động của khách trong `telegram_links` (spec 08). Với liên kết nhóm, chỉ gửi khi mọi chỉ số trong tin thuộc phạm vi của nhóm; nếu không, gửi bản rút gọn chỉ có link.
- Kênh chỉ dùng khi có trong `notify.channels`. Email luôn được gửi cho `report.ready` dù cấu hình thế nào (NFR-12).

### 5.4 Gửi và ghi nhận

- Bảng `notifications`: `id`, `event_id`, `channel`, `recipient_key`, `template`, `template_version`, `status` (`pending`, `sent`, `failed`), `attempts`, `error_code`, `sent_at`. Khóa duy nhất (`event_id`, `channel`, `recipient_key`) để không gửi trùng.
- Thử lại tối đa 3 lần, cách 1, 5, 15 phút. Một kênh lỗi không ảnh hưởng kênh khác.
- Telegram trả lỗi kết nối liên tục trong 30 phút → gửi một thông báo cho team qua email (không qua Telegram).
- Gộp cảnh báo team: cùng (`tenant_id`, `type`, `reason`) trong 6 giờ chỉ gửi một tin, các lần sau tăng bộ đếm, tin kế tiếp sau 6 giờ nêu số lần lặp.
- Mục tiêu: tin gửi đi trong vòng 10 phút kể từ khi sự kiện được phát (FR-OPS-05, FR-REP-05).

## 6. Dữ liệu cho màn hình vận hành (FR-OPS-04)

| Bảng (Postgres) | Ghi bởi | Nội dung |
|---|---|---|
| `pipeline_runs` | Dagster qua API nội bộ | `run_id`, `tenant_id`, `job`, `status` (`running`, `success`, `blocked`, `failed`), `started_at`, `finished_at`, `failed_step`, `blocking_failures` (jsonb) |
| `source_syncs` | Dagster | `tenant_id`, `source`, `account_id`, `last_attempt_at`, `last_success_at`, `last_status`, `last_error_code`, `rows_loaded` |
| `reports` | API (spec 06) | Trạng thái báo cáo |
| `notifications` | Trung tâm thông báo | Mục 5.4 |

`GET /v1/ops/overview` (spec 05) ghép các bảng này thành một dòng mỗi khách. Dữ liệu ghi ngay khi bước kết thúc, nên độ trễ dưới 5 phút.

Giai đoạn 2 (FR-OPS-06): bảng `tenant_costs(month, tenant_id, item, amount_vnd)` nạp từ billing export của GCP (lọc nhãn `tenant_id`), hóa đơn Windsor và Claude chia theo khách; bảng `tenant_hours` nhập tay.

## 7. Chi phí theo khách (NFR-08)

- Mọi dataset có nhãn `tenant_id`.
- dbt: `query-comment` với `job-label: true` và nhãn `tenant_id`, `dx_job=dbt`.
- dlt và Cube: đặt nhãn job BigQuery `tenant_id`, `dx_job=dlt` hoặc `dx_job=cube`.
- Kiểm tra: test đọc cấu hình profile dbt và resource BigQuery, bảo đảm có nhãn.

## 8. Xóa dữ liệu một người mua (FR-OPS-09)

`ops/erase_subject.py --tenant <id> (--phone <số> | --email <email> | --buyer-ref <source>:<mã>) [--dry-run]`

1. Tính `phone_hash` hoặc `email_hash` bằng muối của khách.
2. Tra `transform/pii_columns.yml` (mỗi bảng raw: cột chứa số điện thoại, email, mã người mua) để tìm bản ghi trong `raw`.
3. Xóa bản ghi khớp trong `raw` (với bảng đơn: xóa trường thông tin cá nhân, giữ đơn để không sai doanh thu, đặt `buyer_*` về null).
4. Chạy `tenant_pipeline` với `dbt build --full-refresh` cho các model có thông tin người mua để `stg`, `core`, `marts` không còn bản ghi gốc hay băm.
5. Ghi `erasure_log`: `id`, `tenant_id`, `requested_at`, `completed_at`, `identifier_hash`, `rows_affected`, `operator`. Không ghi giá trị gốc.
6. `--dry-run` chỉ đếm bản ghi.

Quy trình nhận và trả lời yêu cầu nằm trong `ops/runbooks/data-subject-request.md`.

## 9. Runbook bắt buộc

`ops/runbooks/`: `windsor-setup.md`, `marketplace-oauth.md`, `new-tenant.md`, `sync-failed.md`, `test-failed.md`, `telegram-outage.md`, `restore-log.md`, `data-subject-request.md`, `offboarding.md`.

## 10. Kiểm thử

| Test | Nội dung | FR |
|---|---|---|
| `test_fr_ops_01_sync_tenants` | Sửa file, chạy script, API trả cấu hình mới; file lỗi không làm hỏng khách khác | FR-OPS-01 |
| `test_fr_ops_02_bootstrap_idempotent` | Chạy hai lần trên DuckDB, không lỗi, không tạo trùng | FR-OPS-02 |
| `test_fr_ops_03_step_failure_stops_pipeline` | Giả lập lỗi ở từng bước, các bước sau không chạy và phát đúng sự kiện | FR-OPS-03 |
| `test_fr_dq_04_blocked_run_keeps_old_marts` | Cài một test cố ý lỗi; marts và `data_as_of` giữ giá trị cũ; không có `transform.finished` | FR-DQ-04 |
| `test_fr_ing_06_schedule_from_config` | Đổi cron trong cấu hình, sensor mở lần chạy theo cron mới | FR-ING-06 |
| `test_fr_ops_05_team_alert_within_window` | `sync.failed` tạo bản ghi `notifications` cho team trong một vòng worker | FR-OPS-05 |
| `test_fr_ops_08_fake_channel_adapter` | Đăng ký adapter giả lập, tin được gửi qua nó mà không sửa `dispatcher.py` | FR-OPS-08 |
| `test_nfr_12_email_sent_when_telegram_down` | Telegram lỗi, email vẫn gửi | NFR-12 |
| `test_events_idempotent_consumer` | Một sự kiện giao hai lần chỉ được xử lý một lần | |
| `test_fr_ops_09_erase_subject` | Trên dữ liệu mẫu, không còn bản ghi gốc hay băm của người đó | FR-OPS-09 |

## 11. Tiêu chí hoàn thành

- Hai khách giả lập chạy `tenant_pipeline` theo lịch trên `local` và `dev`.
- Sửa `schedule.sync` của `demo_seller`, merge, trong 5 phút lịch mới có hiệu lực.
- Cố ý làm lỗi test đối soát: team nhận tin trong nhóm Telegram nội bộ và email trong 10 phút, nêu ngày, nguồn, mức lệch.
- Mọi test ở mục 10 qua.
