# Spec 01 – Nạp dữ liệu

Hệ thống: S1 (phần nạp). Yêu cầu: FR-ING-01..09, FR-MOD-03 (nguồn tỷ giá).

Phạm vi: connector dlt tự viết, cấu hình Windsor.ai, nguồn `portal`, nguồn tỷ giá, hợp đồng bảng raw. Phần biến đổi nằm ở spec 02.

Tên endpoint của các sàn trong spec này lấy theo tài liệu công khai của nền tảng. Khi cài đặt, đối chiếu lại với tài liệu hiện hành và ghi lại phiên bản API đã dùng trong `pipelines/connectors/<source>/README.md`.

---

## 1. Hợp đồng bảng raw

Mọi công cụ nạp (dlt, Windsor, sau này Airbyte) đều phải tạo ra bảng thỏa hợp đồng này. Spec 02 chỉ dựa vào hợp đồng, không dựa vào công cụ.

- Dataset: `t_<tenant_id>_raw`. Ở `local`: schema DuckDB cùng tên.
- Tên bảng: `<source>__<object>`, chữ thường.
- Cột bắt buộc trên mọi bảng:

| Cột | Kiểu | Nghĩa |
|---|---|---|
| `_dx_loaded_at` | TIMESTAMP (UTC) | Thời điểm bản ghi được nạp |
| `_dx_source_account` | STRING | Mã gian hàng hoặc tài khoản quảng cáo ở nguồn |
| `_dx_record_hash` | STRING | Hash nội dung bản ghi, để phát hiện thay đổi |

- Ghi theo kiểu `merge` theo khóa chính của nguồn. Không xóa bản ghi cũ ở raw.
- Cột lồng nhau được giữ dạng JSON (dlt mặc định tách bảng con; tắt bằng `max_table_nesting=1` với các bảng được liệt kê dưới đây để bảng con có tên ổn định `<table>__<child>`).

### 1.1 Bảng tổng theo ngày để đối soát

Mỗi nguồn bán hàng phải nạp thêm bảng `<source>__daily_totals` với cột `date`, `order_count`, `gross_amount`, `currency`. Số này phải lấy từ một đường độc lập với đường lấy chi tiết đơn khi nền tảng cho phép, để test đối soát (spec 02 mục 5) có nghĩa. Mỗi connector ghi rõ đường lấy trong mục của nó.

## 2. Khung chung cho connector dlt

Đặt ở `pipelines/connectors/<source>/`, mỗi connector gồm:

```
pipelines/connectors/shopee/
  __init__.py
  source.py          # @dlt.source shopee_source(tenant: TenantConfig, account: SourceConfig)
  client.py          # HTTP client: ký request, làm mới token, phân trang, retry
  resources.py       # @dlt.resource cho từng object
  README.md          # phiên bản API, giới hạn, ghi chú
  tests/
    fixtures/        # phản hồi API mẫu (JSON), không chứa dữ liệu thật
    test_source.py
```

### 2.1 Hành vi bắt buộc

| Hành vi | Quy định | FR |
|---|---|---|
| Nạp lịch sử | Lần chạy đầu: lấy 90 ngày gần nhất, hoặc tối đa nền tảng cho phép nếu ít hơn; chia cửa sổ 7 ngày | FR-ING-05 |
| Nạp tăng dần | Con trỏ là thời điểm cập nhật của bản ghi ở nguồn (`update_time` hoặc tương đương), lưu trong dlt state | FR-ING-06 |
| Quét lại | Mỗi lần chạy, lấy lại mọi đơn có thời điểm tạo trong 30 ngày gần nhất mà chưa ở trạng thái cuối (`completed`, `cancelled`, `returned`) | FR-ING-07 |
| Làm mới token | Trước mỗi lần chạy và khi nhận lỗi hết hạn: làm mới, ghi token mới thành phiên bản mới trong Secret Manager | FR-ING-08 |
| Mất quyền | Lỗi xác thực không làm mới được → dừng nguồn đó, phát `sync.failed` với `reason: auth_revoked` | FR-ING-08 |
| Giới hạn tần suất | Tôn trọng giới hạn của nền tảng; retry với backoff lũy thừa có jitter, tối đa 5 lần; lỗi 429 dùng thời gian chờ nền tảng trả về | |
| Không làm lộ dữ liệu | Không log body phản hồi; chỉ log số bản ghi, cửa sổ thời gian, mã lỗi | 00 mục 3.4 |

### 2.2 Bí mật

Mỗi nguồn trong file cấu hình khách có `secret_ref`. Secret là JSON:

```json
{"partner_id": "...", "partner_key": "...", "shop_id": "...", "access_token": "...", "refresh_token": "...", "expires_at": "2026-10-16T10:00:00Z"}
```

`partner_id`, `partner_key` (khóa ứng dụng đối tác của DataxLand) dùng chung mọi khách và nằm ở secret riêng `dx-<source>-app`. Secret theo khách chỉ chứa token của gian hàng.

### 2.3 Cấp quyền cho gian hàng

Mỗi sàn dùng luồng OAuth của nền tảng. API có endpoint bắt đầu và nhận callback (spec 05 mục 6.7). Callback ghi token vào Secret Manager và cập nhật trạng thái nguồn trong Postgres. Trưởng nhóm data thêm `secret_ref` tương ứng vào file cấu hình khách.

## 3. Shopee (FR-ING-01)

Nguồn: Shopee Open Platform API v2. Ký request bằng HMAC-SHA256 theo quy định của nền tảng.

| Bảng raw | Lấy từ | Khóa | Ghi chú |
|---|---|---|---|
| `shopee__orders` | `v2.order.get_order_list` (theo `update_time`) rồi `v2.order.get_order_detail` | `order_sn` | Gồm trạng thái, thời điểm tạo và cập nhật, tổng tiền, thông tin người mua (raw) |
| `shopee__order_items` | Trong chi tiết đơn | `order_sn`, `item_id`, `model_id` | Số lượng, giá gốc, giá sau giảm |
| `shopee__escrow` | `v2.payment.get_escrow_detail` cho đơn đã có quyết toán | `order_sn` | Các khoản phí: hoa hồng, phí dịch vụ, phí giao dịch, phí vận chuyển, trợ giá, tiền thực nhận |
| `shopee__returns` | `v2.returns.get_return_list` và chi tiết | `return_sn` | Lý do, số tiền hoàn, trạng thái |
| `shopee__products` | `v2.product.get_item_list` và thông tin cơ bản | `item_id`, `model_id` | SKU, tên, mã vạch nếu có |
| `shopee__daily_totals` | Đếm từ `get_order_list` theo `create_time` (không gọi chi tiết) | `date` | Đường độc lập với chi tiết đơn |

## 4. TikTok Shop (FR-ING-02)

Nguồn: TikTok Shop Partner API. Phiên bản API ghi trong README của connector.

| Bảng raw | Lấy từ | Khóa | Ghi chú |
|---|---|---|---|
| `tiktok_shop__orders` | Orders search (theo thời gian cập nhật) | `order_id` | |
| `tiktok_shop__order_items` | Trong đơn | `order_id`, `line_item_id` | |
| `tiktok_shop__settlements` | Finance: statement transactions theo đơn | `order_id`, `transaction_id` | Phí, trợ giá, tiền thực nhận |
| `tiktok_shop__returns` | Returns / refunds search | `return_id` | |
| `tiktok_shop__products` | Products search | `product_id`, `sku_id` | |
| `tiktok_shop__daily_totals` | Đếm từ orders search theo thời gian tạo | `date` | |

## 5. Lazada (FR-ING-03)

Nguồn: Lazada Open Platform.

| Bảng raw | Lấy từ | Khóa |
|---|---|---|
| `lazada__orders` | `/orders/get` | `order_id` |
| `lazada__order_items` | `/orders/items/get` | `order_item_id` |
| `lazada__transactions` | `/finance/transaction/details/get` | `transaction_id` |
| `lazada__returns` | Reverse orders API | `reverse_order_id` |
| `lazada__products` | `/products/get` | `item_id`, `sku_id` |
| `lazada__daily_totals` | Đếm từ `/orders/get` theo thời gian tạo | `date` |

## 6. Tỷ giá (FR-MOD-03)

Connector `fx_vcb`, chạy hằng ngày lúc 18:30 giờ Việt Nam, ghi vào dataset dùng chung `dx_ref` (không theo khách).

| Bảng | Khóa | Cột |
|---|---|---|
| `dx_ref.fx_rates` | `date`, `currency` | `rate_vnd` (tỷ giá chuyển khoản bán ra của Vietcombank), `source` = `vcb`, `_dx_loaded_at` |

- Nguồn: dữ liệu tỷ giá công khai của Vietcombank, URL đặt trong `FX_VCB_URL`.
- Ngày không có tỷ giá (cuối tuần, lễ): dùng tỷ giá của ngày làm việc gần nhất trước đó; việc điền ngày trống làm ở spec 02 (`dim_fx_rate`), không làm ở connector.
- Lỗi lấy tỷ giá: phát `sync.failed` với `tenant_id = null`, `source = fx_vcb`. Trưởng nhóm data có thể nhập tay qua `POST /v1/admin/fx-rates` (spec 05).
- Đơn vị tiền cần ở giai đoạn 1: `USD`. Danh sách lấy từ cấu hình, mở rộng được.

## 7. Nguồn `portal`

Dữ liệu khách nhập trên cổng (spec 05 mục 6) được nạp vào raw như mọi nguồn khác.

| Bảng raw | Lấy từ (Postgres) | Khóa |
|---|---|---|
| `portal__product_costs` | `product_costs` của khách | `id` |
| `portal__ad_budgets` | `ad_budgets` của khách | `id` |

- Connector dùng `dlt` nguồn `sql_database`, lọc theo `tenant_id`, chạy ở đầu mỗi lần chạy pipeline của khách.
- Bản ghi bị xóa trên cổng được đánh dấu `deleted_at` ở Postgres (xóa mềm) để raw nhận được trạng thái xóa.

## 8. Windsor.ai (FR-ING-04)

Windsor nạp trực tiếp vào BigQuery; DataxLand không chạy code nạp cho các nguồn này.

### 8.1 Nguồn và bảng

| Nguồn | `source` | Bảng raw theo hợp đồng | Mức chi tiết |
|---|---|---|---|
| Meta Ads | `meta_ads` | `meta_ads__ad_insights_daily` | Ngày × tài khoản × chiến dịch × nhóm quảng cáo |
| TikTok Ads | `tiktok_ads` | `tiktok_ads__ad_insights_daily` | Như trên |
| Google Ads | `google_ads` | `google_ads__ad_insights_daily` | Ngày × tài khoản × chiến dịch × nhóm quảng cáo |
| Amazon Ads | `amazon_ads` | `amazon_ads__ad_insights_daily` | Ngày × profile × chiến dịch × nhóm quảng cáo |
| Amazon Seller Central | `amazon_seller` | `amazon_seller__orders`, `amazon_seller__order_items`, `amazon_seller__financial_events`, `amazon_seller__daily_totals` | Theo đơn |

Trường tối thiểu cho bảng quảng cáo: `date`, `account_id`, `campaign_id`, `campaign_name`, `adgroup_id`, `adgroup_name`, `spend`, `currency`, `impressions`, `clicks`, `conversions`, `conversion_value`.

### 8.2 Ánh xạ về hợp đồng

- Nếu Windsor cho đặt tên bảng và chọn trường: đặt đúng tên ở mục 8.1 và đích là `t_<tenant_id>_raw`.
- Nếu không: Windsor ghi vào `t_<tenant_id>_windsor`, và `ops/bootstrap_tenant.py` tạo view trong `t_<tenant_id>_raw` với đúng tên và cột ở mục 8.1, thêm `_dx_loaded_at` từ cột thời gian đồng bộ của Windsor và `_dx_source_account` từ `account_id`.
- Cấu hình Windsor cho mỗi khách được ghi lại trong `tenants/<id>.yml` (`connector: windsor`, `account_id`) để biết khách nào dùng tài khoản nào. Việc tạo kết nối trên giao diện Windsor là thao tác thủ công, có checklist trong `ops/runbooks/windsor-setup.md`.

### 8.3 Theo dõi

- Dagster không chạy Windsor, nhưng kiểm tra độ tươi: bước `check_windsor_freshness` đọc `max(_dx_loaded_at)` của từng bảng Windsor; quá `freshness_hours` thì phát `sync.failed` với `reason: windsor_stale`.
- Lịch đồng bộ của Windsor đặt theo gói: 3 giờ cho gói Agency, 6 giờ cho gói Seller.

## 9. Hãng vận chuyển (FR-ING-09, giai đoạn 2)

Connector `ghn`, `ghtk`, `jnt` theo cùng khung mục 2. Bảng `<carrier>__shipments` (khóa mã vận đơn) với phí vận chuyển, COD, trạng thái, phí hoàn. Chi tiết viết khi bắt đầu giai đoạn 2.

## 10. Lịch chạy

Lịch đồng bộ của từng khách lấy từ `schedule.sync` trong file cấu hình (spec 04). Mặc định do `ops/bootstrap_tenant.py` điền khi tạo khách:

| Gói | Mặc định |
|---|---|
| `seller` | `0 */6 * * *` |
| `agency` | `0 */3 * * *` |

## 11. Kiểm thử

- Mỗi connector có test với phản hồi giả lập bằng `respx`, phủ: phân trang, làm mới token, lỗi 429, lỗi mất quyền, quét lại đơn đổi trạng thái.
- Test hợp đồng: sau khi chạy với fixture, mọi bảng raw có đủ ba cột bắt buộc và đúng tên.
- `tests/test_fr_ing_07_status_change_after_delivery.py`: fixture có đơn `completed` ở lần 1 và `returned` ở lần 2; sau lần 2, raw có trạng thái mới.

## 12. Tiêu chí hoàn thành

- Connector Shopee và TikTok Shop chạy được với shop thử nghiệm trên `dev`; số đơn và doanh thu 30 ngày khớp Seller Centre trong ngưỡng 1% (FR-ING-01, FR-ING-02).
- Lazada đạt tiêu chí tương tự (FR-ING-03, mốc M4).
- Bảng Windsor của `demo_agency` trên `dev` thỏa hợp đồng ở mục 8.1 (FR-ING-04).
- `fx_rates` có dữ liệu USD liên tục 90 ngày.
- Mọi test ở mục 11 qua trong CI.
