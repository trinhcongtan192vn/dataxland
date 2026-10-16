# Spec 03 – Lớp chỉ số

Hệ thống: S2. Yêu cầu: FR-MET-01..08, FR-INP-03, FR-AGY-01 (cờ cần chú ý), NFR-04, NFR-10.

Phạm vi: thư viện chỉ số YAML, `semantic/build.py`, cấu hình Cube đa khách, bộ máy truy vấn chỉ số trong `services/api`, endpoint `POST /v1/metrics/query`, ba số chính, cờ cần chú ý, phát hiện bất thường, phiên bản chỉ số.

---

## 1. Cấu trúc

```
semantic/
  metrics/
    common/                  # chỉ số dùng cho cả hai gói
    seller/
    agency/
  dimensions.yml             # danh mục chiều phân tích
  sources.yml                # khai báo mart nào là nguồn nào
  build.py
  check_versions.py
  cube/                      # SINH RA – không sửa tay
    model/<mart>.yml
  dist/                      # SINH RA – không sửa tay
    metrics.json             # registry cho services/api
    handbook.json            # sổ tay cho cổng
    ai_context.md            # ngữ cảnh cho AI (GĐ2)
  tests/
cube/
  cube.js                    # cấu hình runtime: auth, đa khách, refresh
```

## 2. Định nghĩa chỉ số (FR-MET-01)

### 2.1 Schema YAML

Một file một chỉ số, tên file trùng `metric`.

| Trường | Bắt buộc | Kiểu | Ghi chú |
|---|---|---|---|
| `metric` | có | chuỗi snake_case | Duy nhất trong toàn thư viện |
| `name_vi` | có | chuỗi | |
| `description_vi` | có | chuỗi | Một đến ba câu, ngôn ngữ của chủ shop |
| `version` | có | semver | Mục 6 |
| `type` | có | `simple` \| `ratio` \| `derived` | Mục 2.2 |
| `source` | với `simple` | tên mart trong `sources.yml` | |
| `measure` | với `simple` | `{agg, column, filters?}` | `agg`: `sum`, `count`, `count_distinct`, `avg`, `min`, `max` |
| `numerator`, `denominator` | với `ratio` | tên chỉ số | |
| `formula` | với `derived` | biểu thức | Chỉ gồm tên chỉ số, số, `+ - * / ( )` |
| `dimensions` | có | danh sách tên trong `dimensions.yml` | Chiều được phép cắt |
| `time_grains` | có | tập con của `day`, `week`, `month` | |
| `unit` | có | `VND` \| `ratio` \| `percent` \| `count` | `ratio` hiển thị dạng `3,2x`; `percent` dạng `12,5%` |
| `good_direction` | có | `up` \| `down` \| `none` | Dùng cho màu và bất thường |
| `packs` | có | tập con của `seller`, `agency` | |
| `hidden` | không | bool, mặc định `false` | Chỉ số phụ để ghép, không hiện trong sổ tay và AI |
| `requires` | không | danh sách: `identity`, `amazon` | Chỉ bật khi khách đủ điều kiện (mục 4.4) |
| `anomaly` | không | `{compare: trailing_4_weeks, threshold_pct, grain: day \| week}` | FR-MET-07 |
| `synonyms_vi` | không | danh sách | Cho AI và tìm kiếm trong sổ tay |
| `source_note_vi` | có | chuỗi | Số lấy từ đâu, diễn giải cho khách |
| `owner` | có | chuỗi | |
| `history` | có | danh sách `{version, date, change_vi}` | Mục 6 |

`build.py` từ chối (thoát mã khác 0, nêu file và trường) khi: thiếu trường bắt buộc, tham chiếu chỉ số không tồn tại, vòng lặp tham chiếu, chiều không có trong `dimensions.yml`, chiều không có trên mart nguồn, hoặc `version` không khớp phần tử cuối của `history`.

### 2.2 Ba loại chỉ số

- **`simple`**: một phép gộp trên một cột của một mart. Sinh thành một measure trong cube của mart đó.
- **`ratio`**: tử chia mẫu. Nếu tử và mẫu cùng mart thì sinh thành measure `number` trong Cube (`{a} / NULLIF({b}, 0)`). Nếu khác mart thì tính ở bộ máy truy vấn (mục 4.2).
- **`derived`**: công thức trên các chỉ số khác. Cùng mart thì sinh measure trong Cube; khác mart thì tính ở bộ máy truy vấn.

Với `ratio` và `derived` khác mart, `dimensions` chỉ được là giao của các chiều của mọi thành phần. `build.py` kiểm tra điều này.

### 2.3 Danh mục chiều

`dimensions.yml` khai báo mỗi chiều và cột tương ứng trên từng mart:

```yaml
date:
  name_vi: Ngày
  type: time
  columns:
    mrt_seller__orders: order_date
    mrt_seller__order_lines: order_date
    mrt_common__ad_daily: date
    mrt_common__sales_daily: date
platform:
  name_vi: Nền tảng
  type: string
  columns:
    mrt_seller__orders: platform
    mrt_seller__order_lines: platform
    mrt_common__ad_daily: platform
    mrt_common__sales_daily: platform
    mrt_agency__budget_monthly: platform
```

Các chiều giai đoạn 1: `date`, `platform`, `channel`, `product`, `campaign`, `adgroup`, `order_status`, `is_provisional`.

## 3. Thư viện chỉ số giai đoạn 1 (FR-MET-03, FR-MET-04)

Công thức dưới đây là bản 1.0.0. Mart viết tắt: `O` = `mrt_seller__orders`, `L` = `mrt_seller__order_lines`, `A` = `mrt_common__ad_daily`, `S` = `mrt_common__sales_daily`, `B` = `mrt_agency__budget_monthly`.

### 3.1 Chỉ số chung (`common/`)

| `metric` | Loại | Định nghĩa | Gói |
|---|---|---|---|
| `ad_spend` | simple | `sum(A.spend_vnd)` | seller, agency |
| `net_revenue_sales` (hidden) | simple | `sum(S.net_revenue_vnd)` | seller, agency |
| `gross_sales` (hidden) | simple | `sum(S.gross_amount_vnd)` | seller, agency |
| `roas_blended` | ratio, khác mart | `net_revenue_sales / ad_spend` | seller, agency |

### 3.2 Gói Seller (`seller/`)

| `metric` | Loại | Định nghĩa |
|---|---|---|
| `gmv` | simple | `sum(O.gross_amount_vnd)` lọc `row_type = 'order'` |
| `net_revenue` | simple | `sum(O.net_revenue_vnd)` |
| `orders_placed` (hidden) | simple | `count(O.order_id)` lọc `row_type = 'order'` |
| `order_count` | simple | `count(O.order_id)` lọc `row_type = 'order'` và `is_cancelled = false` |
| `cancelled_orders` (hidden) | simple | lọc `is_cancelled = true` |
| `returned_orders` (hidden) | simple | lọc `is_returned = true` |
| `aov` | ratio | `net_revenue / order_count` |
| `cancel_rate` | ratio | `cancelled_orders / orders_placed` |
| `return_rate` | ratio | `returned_orders / order_count` |
| `platform_fees` | simple | `sum(O.platform_fee_vnd)` |
| `payment_fees` | simple | `sum(O.payment_fee_vnd)` |
| `shipping_cost` | simple | `sum(O.shipping_cost_vnd)` |
| `return_cost` | simple | `sum(O.return_cost_vnd)` |
| `other_costs` | simple | `sum(O.other_cost_vnd)` |
| `allocated_ad_spend` (hidden) | simple | `sum(O.allocated_ad_spend_vnd)` |
| `cogs` | simple | `sum(O.cogs_vnd)` |
| `contribution_margin` | derived | `net_revenue - cogs - platform_fees - payment_fees - shipping_cost - return_cost` |
| `net_profit_after_fees` | derived | `contribution_margin - allocated_ad_spend - other_costs` |
| `net_margin_pct` | ratio | `net_profit_after_fees / net_revenue` |
| `sku_profit` | derived trên `L` | Cùng công thức `net_profit_after_fees` nhưng trên các cột của `L`; chiều bắt buộc `product` |
| `repeat_customer_rate` | ratio, `requires: [identity]` | Khách có từ 2 đơn trở lên trong kỳ / khách có đơn trong kỳ |

Ghi chú:

- `net_profit_after_fees` dùng `allocated_ad_spend` để cắt được theo kênh và theo SKU. Tổng của nó bằng `ad_spend` nhờ quy tắc phân bổ và dòng `unallocated_cost` (spec 02 mục 4.2, 5).
- Khi khách có SKU thiếu giá vốn, `cogs` coi phần thiếu là 0, và phản hồi API có cảnh báo (mục 4.3). Không đoán giá vốn.

### 3.3 Gói Agency (`agency/`)

| `metric` | Loại | Định nghĩa |
|---|---|---|
| `impressions`, `clicks`, `conversions` | simple | `sum` trên `A` |
| `conversion_value` (hidden) | simple | `sum(A.conversion_value_vnd)` |
| `ctr` | ratio | `clicks / impressions` |
| `cpc` | ratio | `ad_spend / clicks` |
| `cpm` | derived | `ad_spend / impressions * 1000` |
| `cpa` | ratio | `ad_spend / conversions` |
| `roas_platform` | ratio | `conversion_value / ad_spend` |
| `mer` | ratio, khác mart | `gross_sales / ad_spend` |
| `platform_vs_actual_gap` | derived, khác mart | `(conversion_value - net_revenue_sales) / net_revenue_sales` |
| `amazon_ad_spend` (hidden) | simple | `sum(A.spend_vnd)` lọc `platform = 'amazon_ads'` |
| `amazon_ad_sales` (hidden) | simple | `sum(A.conversion_value_vnd)` lọc `platform = 'amazon_ads'` |
| `amazon_total_sales` (hidden) | simple | `sum(S.net_revenue_vnd)` lọc `platform = 'amazon_seller'` |
| `acos` | ratio, `requires: [amazon]` | `amazon_ad_spend / amazon_ad_sales` |
| `tacos` | ratio, khác mart, `requires: [amazon]` | `amazon_ad_spend / amazon_total_sales` |
| `budget` (hidden) | simple | `sum(B.budget_vnd)` |
| `spend_mtd` (hidden) | simple | `sum(B.spend_mtd_vnd)` |
| `budget_used_pct` | ratio | `spend_mtd / budget` |
| `budget_pacing` | derived trên `B` | `spend_mtd / (budget * days_elapsed / days_in_month)`; 1,0 là đúng tiến độ. Chỉ có `time_grains: [month]` |

### 3.4 Kiểm thử giá trị

`semantic/tests/test_values.py` chạy mọi chỉ số không ẩn trên `demo_seller` hoặc `demo_agency` (DuckDB, Cube chạy trong compose) và so với giá trị tính tay ghi trong `semantic/tests/expected/<pack>.yml`. Mỗi chỉ số ít nhất một giá trị (FR-MET-03, FR-MET-04).

## 4. Bộ máy truy vấn và API (FR-MET-05, FR-MET-06)

Module `services/api/app/metrics/`:

| File | Việc |
|---|---|
| `registry.py` | Nạp `semantic/dist/metrics.json` lúc khởi động |
| `cube_client.py` | Gọi Cube REST `/cubejs-api/v1/load` với JWT ký bằng `CUBE_API_SECRET`, payload `{tenant_id, dataset_prefix}` |
| `engine.py` | Phân rã chỉ số, gọi Cube, ghép kết quả, áp công thức |
| `periods.py` | Đổi khoảng thời gian định sẵn sang ngày cụ thể theo giờ Việt Nam |
| `key_numbers.py` | Ba số chính (mục 5) |
| `flags.py` | Cờ cần chú ý (mục 7) |
| `anomaly.py` | Phát hiện bất thường (mục 8) |

### 4.1 `POST /v1/metrics/query`

Khách lấy từ ngữ cảnh xác thực (spec 05 mục 3), không lấy từ body.

**Request**

```json
{
  "metrics": ["net_revenue", "net_profit_after_fees"],
  "dimensions": ["platform"],
  "time": {"preset": "last_week"},
  "grain": "week",
  "filters": [{"dimension": "platform", "op": "in", "values": ["shopee", "tiktok_shop"]}],
  "compare": "previous_period",
  "order": [{"metric": "net_revenue", "dir": "desc"}],
  "limit": 100
}
```

- `time`: `{"preset": ...}` hoặc `{"from": "2026-10-01", "to": "2026-10-15"}` (ngày theo giờ Việt Nam, bao gồm hai đầu). Preset: `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `last_7_days`, `last_30_days`, `last_90_days`.
- `grain`: `day` \| `week` \| `month` \| `none` (mặc định `none`, gộp cả kỳ).
- `compare`: không có, `previous_period`, hoặc `trailing_4_weeks` (trung bình 4 kỳ tuần trước kỳ đang xét). `previous_period` của `this_week` và `this_month` là cùng số ngày tương ứng của tuần hoặc tháng trước (ví dụ thứ Hai–thứ Tư tuần này so với thứ Hai–thứ Tư tuần trước); với kỳ khác là kỳ cùng độ dài ngay trước đó.
- `op`: `eq`, `in`, `not_in`.
- Giới hạn: tối đa 10 chỉ số, 3 chiều, 5.000 dòng.

**Response 200**

```json
{
  "query_id": "01JB…",
  "tenant_id": "demo_seller",
  "time": {"from": "2026-10-05", "to": "2026-10-11", "grain": "week"},
  "metrics": {
    "net_revenue": {"name_vi": "Doanh thu thực nhận", "version": "1.0.0", "unit": "VND"},
    "net_profit_after_fees": {"name_vi": "Lãi sau phí", "version": "1.0.0", "unit": "VND"}
  },
  "rows": [
    {"platform": "shopee", "net_revenue": 152340000, "net_profit_after_fees": 18200000,
     "compare": {"net_revenue": 140100000, "net_profit_after_fees": 20100000}}
  ],
  "data_as_of": "2026-10-16T03:05:00Z",
  "warnings": [
    {"code": "MISSING_COGS", "detail_vi": "3 SKU chưa có giá vốn, chiếm 4.200.000 ₫ doanh thu", "metrics": ["cogs", "net_profit_after_fees"]},
    {"code": "PROVISIONAL", "detail_vi": "12% doanh thu trong kỳ là tạm tính, chưa quyết toán"}
  ]
}
```

- `metric_version` của từng chỉ số nằm trong `metrics.<name>.version`; `data_as_of` lấy từ `mrt_common__data_status` (FR-MET-06).
- Tiền VND trả số nguyên; `ratio` và `percent` trả số thực, `percent` ở thang 0–1.
- Lỗi: `400 METRIC_UNKNOWN`, `400 DIMENSION_NOT_ALLOWED`, `400 GRAIN_NOT_ALLOWED`, `403 METRIC_FORBIDDEN` (mục 4.4), `403 TENANT_FORBIDDEN`, `503 CUBE_UNAVAILABLE`.

### 4.2 Cách bộ máy tính

1. Kiểm tra quyền xem từng chỉ số (mục 4.4).
2. Phân rã mỗi chỉ số thành các measure Cube cần gọi. Nhóm các measure theo cube.
3. Gọi Cube một lần cho mỗi cube, cùng khoảng thời gian, `grain` và chiều. Nếu có `compare`, gọi thêm cho kỳ so sánh.
4. Ghép kết quả theo giá trị chiều (full outer join, thiếu là 0 với `simple`).
5. Áp công thức `ratio` và `derived` khác mart bằng bộ phân tích biểu thức an toàn (không dùng `eval`). Chia cho 0 trả `null`.
6. Thêm `warnings` từ `mrt_common__data_status` khi chỉ số trong yêu cầu bị ảnh hưởng.
7. Ghi nhật ký truy vấn (`query_id`, người gọi, khách, chỉ số, thời gian chạy) vào bảng `metric_queries` để truy vết (NFR-10). Không ghi giá trị trả về.

### 4.3 Cảnh báo dữ liệu (FR-INP-03)

| `code` | Khi nào | Ảnh hưởng |
|---|---|---|
| `MISSING_COGS` | `missing_cogs_sku_count > 0` | `cogs`, `contribution_margin`, `net_profit_after_fees`, `net_margin_pct`, `sku_profit` |
| `PROVISIONAL` | `provisional_revenue_share > 0` | Mọi chỉ số của gói Seller |
| `STALE` | `data_as_of` cũ hơn `freshness_hours` | Mọi chỉ số |

### 4.4 Quyền xem chỉ số

Một chỉ số được trả khi đủ mọi điều kiện:

- Chỉ số thuộc `packs` có chứa `pack` của khách.
- Khách thỏa `requires`: `identity` khi khách có `features.identity: true` trong cấu hình; `amazon` khi khách có nguồn `amazon_ads` hoặc `amazon_seller`.
- Người gọi được xem: `owner`, `data_lead`, `engineer` xem mọi chỉ số; `member` chỉ xem danh sách owner cấp (spec 05 mục 5); `partner` xem chỉ số gói `agency` và chỉ số chung; nhóm Telegram xem theo phạm vi owner chọn (spec 08).
- Chỉ số `hidden` không được gọi trực tiếp qua API công khai, chỉ dùng nội bộ để ghép.

### 4.5 `GET /v1/metrics`

Trả danh sách chỉ số người gọi được xem, mỗi chỉ số kèm dữ liệu sổ tay (mục 9). Dùng cho cổng và AI.

## 5. Ba số chính

`key_numbers.py` là nơi duy nhất định nghĩa ba số chính. Báo cáo tuần, Telegram bot (`/week`, `/month`) và cổng đều gọi qua `GET /v1/metrics/key-numbers?period=<this_week|last_week|this_month|last_month>`.

| Gói | Số 1 | Số 2 | Số 3 |
|---|---|---|---|
| `seller` | `net_revenue` | `net_profit_after_fees` | `% thay đổi net_profit_after_fees` so với kỳ trước |
| `agency` | `ad_spend` | `roas_blended` | `budget_pacing` của tháng chứa ngày cuối kỳ |

Response:

```json
{
  "pack": "seller",
  "period": {"preset": "last_week", "from": "2026-10-05", "to": "2026-10-11"},
  "numbers": [
    {"key": "net_revenue", "label_vi": "Doanh thu thực nhận", "value": 152340000, "unit": "VND", "version": "1.0.0", "change_pct": 0.087},
    {"key": "net_profit_after_fees", "label_vi": "Lãi sau phí", "value": 18200000, "unit": "VND", "version": "1.0.0", "change_pct": -0.094},
    {"key": "net_profit_change_pct", "label_vi": "Lãi so với tuần trước", "value": -0.094, "unit": "percent", "version": "1.0.0"}
  ],
  "data_as_of": "2026-10-16T03:05:00Z",
  "warnings": []
}
```

Số 3 của gói Seller khi lãi kỳ trước bằng 0 hoặc âm: `value = null`, `label_vi` giữ nguyên, kèm `note_vi: "Kỳ trước không có lãi để so sánh"`.

## 6. Phiên bản chỉ số (FR-MET-08)

- Đổi bất kỳ trường nào trong `measure`, `numerator`, `denominator`, `formula`, `source` → phải tăng `version` và thêm phần tử `history`.
  - Đổi làm thay đổi kết quả với cùng dữ liệu: tăng minor (`1.0.0` → `1.1.0`); đổi nghĩa hẳn: tăng major.
  - Chỉ sửa mô tả, tên, từ đồng nghĩa: tăng patch.
- `check_versions.py` (chạy trong CI) so mỗi file với nhánh `main`: đổi trường tính toán mà không tăng `version` → lỗi; tăng `version` mà không có `history` khớp → lỗi; giảm `version` → lỗi.
- Sau khi triển khai, `ops/release_metrics.py` so `metrics.json` mới với bản đang chạy và phát `metric.released` cho mỗi chỉ số đổi phiên bản (spec 04).
- Báo cáo lưu ảnh chụp số liệu kèm `version` lúc dựng (spec 06), nên báo cáo cũ không bị tính lại.

## 7. Cờ cần chú ý (gói Agency)

`flags.py` tính ba quy tắc. Ngưỡng lấy từ `attention` trong cấu hình khách, nếu không có thì dùng mặc định.

| Mã | Quy tắc | Phạm vi | Ngưỡng mặc định |
|---|---|---|---|
| `OVERSPEND` | `budget_pacing > 1 + overspend_pct/100` trong tháng hiện tại | Theo nền tảng | `overspend_pct: 15` |
| `ROAS_DROP` | `roas_blended` 7 ngày gần nhất thấp hơn trung bình 4 tuần trước đó quá `roas_drop_pct` | Theo khách | `roas_drop_pct: 25` |
| `PLATFORM_OVERCLAIM` | `roas_platform` của nền tảng lớn hơn `roas_blended` của khách quá `platform_gap_pct` | Theo nền tảng, 7 ngày gần nhất | `platform_gap_pct: 50` |

- Endpoint `GET /v1/metrics/flags` trả danh sách cờ đang bật: `{code, platform?, value, threshold, message_vi}`.
- Dùng ở trang agency (FR-AGY-01), dashboard và báo cáo tuần gói Agency (FR-REP-03).
- Quy tắc cũng có thể bật cho gói Seller có quảng cáo, nhưng giai đoạn 1 chỉ hiển thị ở gói Agency.

## 8. Phát hiện bất thường (FR-MET-07)

- Chạy ở bước "bất thường" trong pipeline của khách (spec 04), sau khi làm mới Cube, qua `POST /v1/internal/anomalies/run` (token nội bộ).
- Với mỗi chỉ số có khối `anomaly` và thuộc gói của khách: so giá trị của kỳ gần nhất đã đủ ngày (`grain: day` → hôm qua; `grain: week` → tuần trước) với trung bình 4 kỳ cùng loại trước đó.
- Lệch tuyệt đối quá `threshold_pct` → phát `metric.anomaly` với payload `{metric, version, grain, period, value, baseline, diff_pct, direction}`. `direction` là `good` hoặc `bad` theo `good_direction`.
- Không phát trùng: khóa `(tenant_id, metric, grain, period)` chỉ phát một lần.
- Không chạy khi lần chạy đang bị chặn bởi test (spec 04 mục 3).

## 9. `semantic/build.py` (FR-MET-02)

Đầu vào: `metrics/**/*.yml`, `dimensions.yml`, `sources.yml`. Đầu ra:

| File | Nội dung |
|---|---|
| `cube/model/<mart>.yml` | Một cube cho mỗi mart; measure cho chỉ số `simple` và chỉ số `ratio`/`derived` cùng mart; dimension theo `dimensions.yml`; pre-aggregation (mục 10.2) |
| `dist/metrics.json` | Mọi chỉ số đã chuẩn hóa: loại, thành phần, chiều, grain, đơn vị, phiên bản, `requires`, `hidden`, `packs`, cube và measure tương ứng |
| `dist/handbook.json` | Cho sổ tay: `metric`, `name_vi`, `description_vi`, công thức diễn giải bằng tên tiếng Việt của thành phần, `source_note_vi`, `unit`, `version`, `history`, `synonyms_vi`, `packs` |
| `dist/ai_context.md` | Bảng chỉ số và từ đồng nghĩa cho AI (GĐ2) |

- Đầu ra ổn định: sắp xếp khóa và danh sách, để `git diff --exit-code` trong CI có nghĩa.
- Mỗi cube có `sql_table: "{COMPILE_CONTEXT.securityContext.dataset_prefix}_marts.<mart>"`.
- Measure lọc (`filters` của chỉ số) sinh thành `filters` của measure trong Cube.

## 10. Cube runtime

### 10.1 Đa khách (`cube/cube.js`)

| Hook | Hành vi |
|---|---|
| `checkAuth` | Xác minh JWT HS256 bằng `CUBE_API_SECRET`. Thiếu `tenant_id` hoặc `dataset_prefix`, hoặc `tenant_id` không khớp quy ước tên → từ chối |
| `contextToAppId` | `CUBE_APP_<tenant_id>` |
| `contextToOrchestratorId` | `CUBE_ORCH_<tenant_id>` |
| `queryRewrite` | Từ chối mọi truy vấn khi `securityContext.tenant_id` trống |
| `scheduledRefreshContexts` | Gọi `GET /v1/internal/tenants?status=active` để lấy danh sách khách |
| `driverFactory` | `local`: DuckDB, file `DUCKDB_PATH`. `dev`/`prod`: BigQuery với tài khoản dịch vụ `dx-cube`, chỉ có quyền đọc các dataset `*_marts` |

Chỉ `services/api` gọi Cube. Cube không mở ra ngoài (spec 00 mục 7).

### 10.2 Pre-aggregation (NFR-04)

- Mỗi cube có một rollup theo `day` với các chiều thường dùng (`platform`, `channel`) và mọi measure cộng được. Cube `mrt_seller__order_lines` có thêm rollup theo `product`.
- Không đặt `refreshKey` theo thời gian. Làm mới khi nhận `transform.finished` của khách: bước `refresh_cube` của Dagster gọi API build pre-aggregation của Cube cho `securityContext` của khách đó (spec 04 mục 3).
- Mục tiêu: `POST /v1/metrics/query` p95 dưới 2 giây trên dữ liệu 12 tháng của một khách.

## 11. Kiểm thử

| Test | Nội dung | FR |
|---|---|---|
| `test_fr_met_01_build_rejects_invalid_yaml` | Mỗi lỗi ở mục 2.1 cho một thông báo rõ | FR-MET-01 |
| `test_fr_met_02_generated_models_match` | Chạy `build.py` hai lần cho kết quả giống hệt | FR-MET-02 |
| `test_fr_met_05_cube_rejects_missing_tenant` | JWT không có `tenant_id` bị từ chối | FR-MET-05 |
| `test_fr_met_05_cube_tenant_isolation` | Cùng truy vấn với `demo_seller` và `demo_agency` sinh SQL đọc đúng dataset của từng khách | FR-MET-05 |
| `test_fr_met_06_response_has_version_and_as_of` | Mọi phản hồi có `version` và `data_as_of` | FR-MET-06 |
| `test_fr_met_07_anomaly_40pct` | Số giả lập lệch 40% so với trung bình 4 tuần phát `metric.anomaly` một lần | FR-MET-07 |
| `test_fr_met_08_version_check` | Đổi `formula` không tăng version thì `check_versions.py` lỗi | FR-MET-08 |
| `test_key_numbers_seller_agency` | Ba số chính khớp `expected/<pack>.yml` | |
| `test_flags_defaults_and_override` | Mỗi quy tắc bật đúng ở ngưỡng mặc định và ngưỡng ghi đè | FR-AGY-01 |
| `test_fr_inp_03_missing_cogs_warning` | `demo_seller` có SKU thiếu giá vốn thì phản hồi có `MISSING_COGS` | FR-INP-03 |

## 12. Tiêu chí hoàn thành

- `make semantic` sinh đủ file ở mục 9; CI báo lỗi khi file sinh ra lệch.
- Mọi chỉ số ở mục 3 có trong thư viện và qua test giá trị.
- `POST /v1/metrics/query`, `GET /v1/metrics`, `GET /v1/metrics/key-numbers`, `GET /v1/metrics/flags` chạy với hai khách giả lập.
- Mọi test ở mục 11 qua.
