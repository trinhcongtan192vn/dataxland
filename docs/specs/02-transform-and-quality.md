# Spec 02 – Biến đổi và chất lượng dữ liệu

Hệ thống: S1 (phần biến đổi). Yêu cầu: FR-MOD-01..05, FR-DQ-01..04, NFR-03, NFR-07.

Phạm vi: dự án dbt trong `transform/`, từ bảng raw (spec 01) tới bảng marts mà Cube đọc (spec 03), cùng các test chất lượng.

---

## 1. Cấu trúc dự án dbt

```
transform/
  dbt_project.yml
  profiles.yml               # đọc từ biến môi trường, không chứa bí mật
  packages.yml               # dbt_utils, elementary
  macros/
    generate_schema_name.sql
    cross_db/                # macro đa nền tảng, mục 7
    dx_union_enabled.sql
    to_vnd.sql
    pii_hash.sql
  models/
    sources.yml              # khai báo nguồn raw, freshness
    staging/
      shopee/  tiktok_shop/  lazada/  amazon_seller/
      meta_ads/  tiktok_ads/  google_ads/  amazon_ads/
      portal/  fx/
      <source>_file/         # adapter file cho kiểm tra sức khỏe (spec 07)
    core/
    marts/
      seller/
      agency/
      common/
  seeds/
    status_map__<source>.csv
    return_reason_map__<source>.csv
    fee_type_map__<source>.csv
    platform_map.csv
  tests/
    generic/
      reconcile_daily_totals.sql
      sum_preserved.sql
    singular/
  samples/                   # dữ liệu mẫu raw (spec 00 mục 5)
  scripts/
    check_portability.py
```

### 1.1 Biến dbt

Dagster truyền biến khi gọi `dbt build` cho một khách (spec 04 mục 3). Giá trị lấy từ file cấu hình khách.

| Biến | Kiểu | Ví dụ | Nguồn |
|---|---|---|---|
| `tenant_id` | chuỗi | `demo_seller` | `tenant_id` |
| `pack` | chuỗi | `seller` | `pack` |
| `sources` | danh sách | `[shopee, tiktok_shop, meta_ads, portal]` | `sources[].type` |
| `cost_allocation` | chuỗi | `by_revenue` | `cost_allocation` |
| `freshness_hours` | số | `6` | `quality.freshness_hours` |
| `reconcile_tolerance_pct` | map | `{default: 1.0, lazada: 2.0}` | `quality.reconcile_tolerance_pct` |
| `provisional_window_days` | map | `{default: 14, shopee: 14}` | `quality.provisional_window_days` |
| `dataset_prefix` | chuỗi | `t_demo_seller` hoặc `hc_01jb8x` | Dagster tính |

Muối băm thông tin cá nhân không là biến dbt. Nó được đọc bằng `env_var('DX_PII_SALT')`, Dagster lấy từ secret `dx-<tenant_id>-pii-salt` và đặt vào môi trường của tiến trình dbt.

### 1.2 Dataset theo lớp

Macro `generate_schema_name` trả `<dataset_prefix>_<layer>`, với `layer` là `stg`, `core`, `marts` theo thư mục model. Bảng raw đọc qua `sources.yml` với `schema: "{{ var('dataset_prefix') }}_raw"`.

Ở `local`, mọi dataset là schema trong cùng file DuckDB.

### 1.3 Bật tắt adapter theo nguồn

Mỗi model staging có:

```sql
{{ config(enabled = 'shopee' in var('sources', [])) }}
```

Core không tham chiếu trực tiếp model staging của một nguồn, mà gọi macro `dx_union_enabled('orders')`. Macro này ghép (`UNION ALL`) mọi model `stg_<source>__orders` đang bật. Nhờ vậy thêm nguồn mới chỉ cần thêm thư mục staging.

Để `ref` hoạt động với model bị tắt, macro dùng `graph.nodes` để chỉ lấy model đang bật.

## 2. Quy ước model

| Lớp | Tên | Vật liệu hóa | Ghi chú |
|---|---|---|---|
| Staging | `stg_<source>__<object>` | `view` | Một model cho một bảng raw |
| Trung gian | `int_<topic>` | `ephemeral` hoặc `table` | Chỉ trong `core/` |
| Core | `dim_<entity>`, `fct_<entity>` | `table` (BigQuery: phân vùng theo ngày nếu có cột ngày) | |
| Marts | `mrt_<pack>__<topic>` | `table` | Cube đọc trực tiếp |

Cột chung cho mọi model core và marts: `tenant_id`, `_dx_updated_at`. Bảng core có thêm `source`, `source_id`.

Khóa sinh trong core dùng `dbt_utils.generate_surrogate_key` trên (`source`, `source_id`) hoặc các trường được nêu ở mục 4.

## 3. Staging (FR-MOD-01)

### 3.1 Việc của staging

1. Đổi tên cột về tên chuẩn (mục 3.2).
2. Ép kiểu. Timestamp về UTC; thêm cột ngày nghiệp vụ theo `Asia/Ho_Chi_Minh` (spec 00 mục 3.2).
3. Chuẩn hóa trạng thái, lý do hoàn, loại phí qua seed và bảng ghi đè (mục 3.3).
4. Quy đổi tiền: giữ `*_original`, `currency`, thêm `*_vnd` qua macro `to_vnd` (mục 3.4).
5. Khử trùng theo khóa nguồn: giữ bản ghi có `_dx_loaded_at` mới nhất.
6. Giữ thông tin cá nhân người mua dạng gốc ở đây, đồng thời sinh cột băm `buyer_phone_hash`, `buyer_email_hash` bằng macro `pii_hash` để core chỉ lấy cột băm.

Hàm riêng của BigQuery chỉ được dùng ở lớp này (NFR-07).

### 3.2 Hợp đồng đầu ra theo loại đối tượng

Mọi model staging cùng loại phải có đủ các cột dưới đây, cùng tên và cùng kiểu. Mỗi model bật `contract: enforced: true` của dbt và khai báo cột trong YAML để dbt kiểm tra.

**`stg_<source>__orders`**

| Cột | Kiểu |
|---|---|
| `source`, `source_id` (mã đơn), `source_account` | string |
| `ordered_at`, `updated_at` | timestamp |
| `order_date` | date |
| `status_raw`, `status` | string |
| `buyer_ref` | string (mã người mua của sàn, nếu có) |
| `buyer_phone_hash`, `buyer_email_hash` | string, có thể null |
| `currency` | string |
| `gross_amount_original`, `discount_amount_original`, `seller_discount_original`, `platform_discount_original` | numeric |
| `gross_amount_vnd`, `discount_amount_vnd`, `net_amount_vnd` | numeric |
| `settled_at` | timestamp, null nếu chưa quyết toán |

**`stg_<source>__order_lines`**: `source`, `source_id` (mã dòng), `order_source_id`, `seller_sku`, `item_name`, `quantity`, `unit_price_vnd`, `line_gross_vnd`, `allocated_discount_vnd`.

**`stg_<source>__fees`**: `source`, `source_id`, `order_source_id` (null nếu không gắn đơn), `source_account`, `fee_date`, `fee_type_raw`, `cost_type`, `amount_original`, `currency`, `amount_vnd`. Phí được ghi số dương là tiền khách phải trả.

**`stg_<source>__returns`**: `source`, `source_id`, `order_source_id`, `order_line_source_id` (null nếu cả đơn), `returned_at`, `return_date`, `reason_raw`, `reason`, `refund_amount_vnd`, `return_fee_vnd`, `status`.

**`stg_<source>__products`**: `source`, `source_id`, `seller_sku`, `name`, `barcode`, `category_raw`.

**`stg_<source>__ad_insights_daily`**: `source`, `source_account`, `date`, `campaign_id`, `campaign_name`, `adgroup_id`, `adgroup_name`, `currency`, `spend_original`, `spend_vnd`, `impressions`, `clicks`, `conversions`, `conversion_value_original`, `conversion_value_vnd`.

**`stg_<source>__daily_totals`**: `source`, `source_account`, `date`, `order_count`, `gross_amount_vnd`.

**`stg_portal__product_costs`**: `source_id`, `seller_sku`, `unit_cost_vnd`, `valid_from` (date), `deleted`.

**`stg_portal__ad_budgets`**: `source_id`, `platform`, `month` (date, ngày 1), `budget_vnd`, `deleted`.

**`stg_fx__rates_daily`**: `date`, `currency`, `rate_vnd`. Điền mọi ngày từ ngày sớm nhất có tỷ giá đến hôm nay; ngày trống lấy tỷ giá của ngày gần nhất trước đó.

### 3.3 Ánh xạ trạng thái và ghi đè (FR-MOD-01, FR-MOD-04)

- Seed `status_map__<source>.csv`: `status_raw,status`. Tương tự `return_reason_map__<source>.csv` (`reason_raw,reason`) và `fee_type_map__<source>.csv` (`fee_type_raw,cost_type`).
- Bộ trạng thái chuẩn: `pending`, `confirmed`, `shipping`, `delivered`, `completed`, `cancelled`, `returned`, `failed_delivery`.
- Bộ lý do hoàn chuẩn: `buyer_changed_mind`, `damaged`, `wrong_item`, `not_received`, `quality`, `failed_delivery`, `other`.
- Ghi đè theo khách: file `tenants/overrides/<tenant_id>_status_map.csv` (cùng cột, thêm cột `source`). Dagster nạp file này vào `<prefix>_raw.dx__status_map_override` trước `dbt build` (spec 04). Staging dùng giá trị ghi đè nếu có, nếu không thì dùng seed.
- Test `accepted_values` trên cột `status`, `reason`, `cost_type`: trạng thái chưa được map (null sau ánh xạ) làm test lỗi, mức chặn.

### 3.4 Quy đổi tiền (FR-MOD-03)

```sql
{{ to_vnd('gross_amount', 'currency', 'order_date') }}
```

- `currency = 'VND'`: giữ nguyên.
- Khác: nhân với `rate_vnd` của `stg_fx__rates_daily` tại ngày giao dịch (`order_date`, `fee_date` hoặc `date` của quảng cáo).
- Không có tỷ giá cho ngày đó: kết quả null và test `not_null` trên cột `*_vnd` lỗi, mức chặn.

### 3.5 Băm thông tin cá nhân (NFR-03)

`pii_hash(column, kind)`:

- `kind = 'phone'`: bỏ ký tự không phải số, đổi đầu `84` thành `0`, rồi băm.
- `kind = 'email'`: cắt khoảng trắng, chữ thường, rồi băm.
- Băm: SHA-256 hex của `salt || value`, với `salt` từ `env_var('DX_PII_SALT')`.
- Giá trị rỗng hoặc bị sàn che (ví dụ chứa `*`): trả null.

## 4. Core (FR-MOD-02)

| Model | Từ | Khóa | Cách sinh khóa |
|---|---|---|---|
| `dim_channel` | `sources` var + `source_account` trong staging | `channel_id` | key(`source`, `source_account`) |
| `dim_product` | `stg_*__products`, `seller_sku` trong dòng đơn | `product_id` | GĐ1: key(lower(trim(`seller_sku`))); SKU trống thì key(`source`, `source_id`). GĐ2: áp `identity_map` (spec 10) |
| `dim_product_cost` | `stg_portal__product_costs` | `product_id`, `valid_from` | `valid_to` = `valid_from` của bản kế tiếp trừ 1 ngày, bản cuối là null |
| `dim_ad_budget` | `stg_portal__ad_budgets` | `channel_id`, `month` | Ngân sách nhập theo `platform`; nếu khách có nhiều tài khoản trên một nền tảng thì gán cho `channel_id` theo `platform` và chia đều. Ghi chú trong YAML của model |
| `dim_customer` | `buyer_ref`, cột băm của đơn | `customer_id` | GĐ1: key(`source`, `buyer_ref`); không có `buyer_ref` thì key(`phone_hash`); không có gì thì null. GĐ2: áp `identity_map` |
| `fct_order` | `dx_union_enabled('orders')` | `order_id` | key(`source`, `source_id`) |
| `fct_order_line` | `dx_union_enabled('order_lines')` | `order_line_id` | key(`source`, `source_id`) |
| `fct_cost` | `dx_union_enabled('fees')` + chi quảng cáo từ `fct_ad_performance_daily` | `cost_id` | key(`source`, `source_id`) hoặc key(`channel_id`, `date`, `'ad_spend'`) |
| `fct_return` | `dx_union_enabled('returns')` | `return_id` | key(`source`, `source_id`) |
| `fct_ad_performance_daily` | `dx_union_enabled('ad_insights_daily')` | `channel_id`, `campaign_id`, `adgroup_id`, `date` | |
| `fct_cost_allocated` | `fct_cost`, `fct_order` | `cost_id`, `order_id` | Mục 4.2 |

Trường chính của mỗi bảng theo `architecture.md` mục 5.3. Các cột thêm dưới đây là bắt buộc.

### 4.1 Cột thêm của `fct_order`

| Cột | Nghĩa |
|---|---|
| `order_date` | Ngày đặt theo giờ Việt Nam |
| `is_settled` | Có bản ghi quyết toán (`settled_at` không null) |
| `is_provisional` | `not is_settled` và `order_date` trong `provisional_window_days` của sàn đó tính đến hôm nay |
| `is_final_status` | `status` thuộc `completed`, `cancelled`, `returned`, `failed_delivery` |
| `cogs_vnd` | Tổng (`quantity` × `unit_cost` hiệu lực tại `order_date`) của các dòng; null nếu có dòng thiếu giá vốn |
| `has_missing_cogs` | Có ít nhất một dòng thiếu giá vốn |

Đơn hủy trước khi giao có `net_amount_vnd = 0` trong tính doanh thu thực nhận; giữ `gross_amount_vnd` để tính `cancel_rate`.

Với đơn chưa quyết toán, phí lấy theo ước tính có trong chi tiết đơn của sàn nếu có; nếu sàn không cung cấp thì phí bằng 0 và đơn được đánh dấu `is_provisional`. Lớp chỉ số trả tỷ lệ doanh thu tạm tính để cổng hiển thị (spec 03 mục 4).

### 4.2 Phân bổ chi phí (FR-MOD-05)

`fct_cost_allocated` có một dòng cho mỗi cặp (khoản chi, đơn nhận phân bổ), cùng `allocated_amount_vnd`.

| `cost_allocation` | Khoản đã gắn đơn | Khoản chưa gắn đơn (gắn kênh hoặc ngày) |
|---|---|---|
| `by_revenue` | Giữ nguyên | Chia cho các đơn không hủy trong cùng ngày (và cùng kênh nếu khoản có `channel_id` là kênh bán) theo tỷ lệ `net_amount_vnd` |
| `by_order` | Giữ nguyên | Chia đều theo số đơn không hủy |
| `none` | Giữ nguyên | Một dòng với `order_id = null` |

- Chi quảng cáo (`channel_id` là tài khoản quảng cáo) được chia cho mọi kênh bán của khách trong cùng ngày.
- Ngày không có đơn để nhận: giữ một dòng với `order_id = null`.
- Test generic `sum_preserved`: tổng `allocated_amount_vnd` theo `cost_id` bằng `amount_vnd` của `fct_cost`, sai lệch tối đa 1 đồng do làm tròn. Mức chặn.

## 5. Marts

Marts là bảng phẳng, đã gộp, cho Cube đọc. Cột tiền đều là VND.

| Model | Gói | Mức chi tiết | Cột chính |
|---|---|---|---|
| `mrt_seller__orders` | seller | Một đơn | `order_id`, `order_date`, `channel_id`, `platform`, `status`, `is_provisional`, `customer_id`, `gross_amount_vnd`, `net_revenue_vnd`, `platform_fee_vnd`, `payment_fee_vnd`, `shipping_cost_vnd`, `allocated_ad_spend_vnd`, `other_cost_vnd`, `return_cost_vnd`, `cogs_vnd`, `has_missing_cogs`, `is_cancelled`, `is_returned` |
| `mrt_seller__order_lines` | seller | Một dòng đơn | `order_line_id`, `order_id`, `order_date`, `channel_id`, `platform`, `product_id`, `seller_sku`, `product_name`, `quantity`, `net_revenue_vnd`, các phí đã phân bổ xuống dòng theo tỷ lệ doanh thu dòng, `cogs_vnd`, `has_missing_cogs`, `is_returned` |
| `mrt_common__ad_daily` | seller, agency | Ngày × kênh quảng cáo × chiến dịch × nhóm | `date`, `channel_id`, `platform`, `account_id`, `campaign_id`, `campaign_name`, `adgroup_id`, `adgroup_name`, `spend_vnd`, `impressions`, `clicks`, `conversions`, `conversion_value_vnd` |
| `mrt_common__sales_daily` | seller, agency | Ngày × kênh bán | `date`, `channel_id`, `platform`, `order_count`, `gross_amount_vnd`, `net_revenue_vnd`, `amazon_ad_sales_vnd` (cho ACOS), `cancelled_count`, `returned_count` |
| `mrt_agency__budget_monthly` | agency | Tháng × nền tảng | `month`, `platform`, `budget_vnd`, `spend_mtd_vnd`, `days_in_month`, `days_elapsed` |
| `mrt_common__data_status` | cả hai | Một dòng | `data_as_of` (min theo nguồn của `max(_dx_loaded_at)`), `provisional_revenue_share`, `missing_cogs_sku_count`, `missing_cogs_revenue_vnd` |

`mrt_seller__orders` có cột `row_type`: `order` cho đơn, `unallocated_cost` cho khoản chi không phân bổ được vào đơn nào (mục 4.2), với `order_id = 'unallocated:' || cost_id` và các cột doanh thu bằng 0. Nhờ vậy tổng chi phí và lãi luôn đủ dù khách chọn `none`. Chỉ số đếm đơn lọc `row_type = 'order'` (spec 03).

Marts của gói không dùng bị tắt bằng `enabled = var('pack') in [...]`.

Lấy `net_revenue_vnd` của đơn: `net_amount_vnd` trừ `refund_amount_vnd` của các lần hoàn thuộc đơn đó; đơn hủy là 0.

## 6. Kiểm tra chất lượng (FR-DQ-01..04)

### 6.1 Danh sách test

| Test | Cài đặt | Mức | FR |
|---|---|---|---|
| Độ tươi nguồn | `freshness` trong `sources.yml`: `error_after: {count: "{{ var('freshness_hours') }}", period: hour}`, `loaded_at_field: _dx_loaded_at`. Không áp dụng cho `portal` và bảng `daily_totals` | Chặn | FR-DQ-01 |
| Khóa | `unique`, `not_null` trên khóa mọi model core và marts | Chặn | FR-MOD-02 |
| Quan hệ | `relationships`: `fct_order.channel_id` → `dim_channel`, `fct_order_line.order_id` → `fct_order`, `fct_order_line.product_id` → `dim_product`, `fct_return.order_line_id` → `fct_order_line` (nếu không null), `fct_cost.order_id` → `fct_order` (nếu không null) | Chặn | FR-MOD-02 |
| Ánh xạ | `accepted_values` trên `status`, `reason`, `cost_type` | Chặn | FR-MOD-01 |
| Tỷ giá | `not_null` trên mọi cột `*_vnd` | Chặn | FR-MOD-03 |
| Đối soát | Generic `reconcile_daily_totals` trên `fct_order` theo từng nguồn bán | Chặn | FR-DQ-02 |
| Phân bổ | Generic `sum_preserved` trên `fct_cost_allocated` | Chặn | FR-MOD-05 |
| Khối lượng | Elementary `volume_anomalies` trên `fct_order`, `fct_ad_performance_daily` | Cảnh báo | FR-DQ-03 |
| Thiếu giá vốn | Singular test đếm SKU có doanh thu 30 ngày mà thiếu giá vốn | Cảnh báo | FR-INP-03 |

Mức chặn dùng `severity: error`, mức cảnh báo dùng `severity: warn`. Dagster quyết định chặn dựa trên `status = fail` và `severity = error` trong `run_results.json` (spec 04 mục 3).

### 6.2 Test đối soát

`reconcile_daily_totals(source)`:

- So `fct_order` (đếm đơn và tổng `gross_amount_vnd` theo `order_date`, lọc theo `source`) với `stg_<source>__daily_totals`.
- Chỉ xét các ngày từ D-30 đến D-1 (bỏ hôm nay vì chưa đủ ngày).
- Lỗi khi `abs(lệch) / số của nguồn × 100 > ngưỡng`, ngưỡng là `reconcile_tolerance_pct[source]` hoặc `reconcile_tolerance_pct.default`, mặc định 1.0.
- Mỗi dòng lỗi trả: `source`, `date`, `metric` (`order_count` hoặc `gross_amount`), `expected`, `actual`, `diff_pct`. Dagster đọc các dòng này (`store_failures: true`) để đưa vào thông báo (spec 04 mục 5).

### 6.3 Hành vi khi có test chặn (FR-DQ-04)

Do Dagster thực hiện, mô tả ở spec 04 mục 3. Về phía dbt:

- Marts được build vào bảng tạm có hậu tố `__staging` rồi hoán đổi tên chỉ khi toàn bộ test chặn qua. Cài đặt bằng post-hook hoặc bước `swap_marts` của Dagster gọi macro `dx_swap_marts()`.
- Nhờ vậy khi test lỗi, Cube vẫn đọc marts của lần chạy tốt trước, và `mrt_common__data_status.data_as_of` vẫn là thời điểm cũ.

## 7. Tính đa nền tảng (NFR-07)

- Trong `core/` và `marts/`: chỉ dùng hàm SQL chuẩn và macro cross-db của dbt (`dbt.date_trunc`, `dbt.dateadd`, `dbt.datediff`, `dbt.safe_cast`, `dbt.concat`, `dbt.hash`, `dbt.type_*`) hoặc macro trong `macros/cross_db/`.
- `scripts/check_portability.py` quét file SQL trong `core/` và `marts/`, báo lỗi khi gặp từ khóa riêng của BigQuery: `SAFE_CAST`, `SAFE_DIVIDE`, `FORMAT_DATE`, `PARSE_DATE`, `PARSE_TIMESTAMP`, `DATE_TRUNC(` dạng BigQuery, `ARRAY_AGG`, `STRUCT(`, `UNNEST`, `QUALIFY`, `` ` `` (backtick). Script chạy trong `make lint`.
- CI chạy toàn bộ model trên DuckDB (spec 00 mục 8.1). Đó là bằng chứng chính cho NFR-07.

## 8. Dữ liệu mẫu và test giá trị

- `make seed-local` nạp `transform/samples/` vào `t_demo_seller_raw` và `t_demo_agency_raw` của DuckDB.
- Mỗi model core và marts có ít nhất một unit test dbt (`unit_tests:` trong YAML) với dữ liệu đầu vào nhỏ và kết quả mong đợi tính tay. Bắt buộc cho: ánh xạ trạng thái, quy đổi tiền, giá vốn theo ngày hiệu lực, phân bổ chi phí, `is_provisional`, `net_revenue_vnd` khi có hoàn.
- Dữ liệu mẫu phải có: một đơn USD (Amazon), một ngày cuối tuần không có tỷ giá, một trạng thái lạ chỉ có trong file ghi đè của `demo_seller`, một SKU đổi giá vốn giữa kỳ.

## 9. Tiêu chí hoàn thành

- `make dbt-build TENANT=demo_seller` và `TENANT=demo_agency` chạy xanh trên DuckDB và trên BigQuery `dev`.
- Thêm một dòng trạng thái lạ vào dữ liệu mẫu làm test ánh xạ lỗi; thêm dòng đó vào file ghi đè thì test qua (FR-MOD-01, FR-MOD-04).
- Unit test đổi giá vốn từ một ngày chỉ ảnh hưởng đơn từ ngày đó (FR-INP-01).
- `sum_preserved` qua với cả ba cách phân bổ (FR-MOD-05).
- Làm lệch 2% doanh thu một ngày trong `daily_totals` mẫu thì `reconcile_daily_totals` lỗi và trả đúng ngày, nguồn, mức lệch (FR-DQ-02).
- Không cột nào trong `*_core` và `*_marts` chứa số điện thoại hoặc email dạng gốc: test quét tên cột và mẫu giá trị (NFR-03).
- `check_portability.py` không báo lỗi.
