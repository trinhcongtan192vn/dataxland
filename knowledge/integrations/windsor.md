# Windsor.ai (quảng cáo và Amazon Seller)

Meta Ads, TikTok Ads, Google Ads, Amazon Ads và Amazon Seller Central được nạp bằng Windsor.ai, ghi thẳng vào BigQuery (spec 01 §8). DataxLand không chạy code nạp cho các nguồn này; Dagster chỉ kiểm tra độ tươi.

## 1. Tài khoản Windsor (làm một lần)

1. Đăng ký **windsor.ai** bằng email công ty, chọn gói có **BigQuery destination**.
2. **Settings → API key**: sao chép khóa vào biến `WINDSOR_API_KEY` (chỉ dùng để kiểm tra trạng thái, không bắt buộc).
3. **Destinations → BigQuery**: cấp cho service account của Windsor quyền `BigQuery Data Editor` trên dataset đích của từng khách (`t_<tenant_id>_raw`, hoặc `t_<tenant_id>_windsor` nếu không đặt được tên bảng).

## 2. Kết nối tài khoản quảng cáo của khách

Với mỗi nền tảng, trong Windsor chọn **Connectors → <nền tảng> → Add account**, đăng nhập bằng tài khoản có quyền đọc của khách:

| Nền tảng | Quyền tối thiểu khách cần cấp | `account_id` ghi vào `tenants/<id>.yml` |
|---|---|---|
| Meta Ads | Business Manager: quyền **View performance** trên tài khoản quảng cáo | `act_<số>` |
| TikTok Ads | TikTok Business Center: **Analyst** | Advertiser ID |
| Google Ads | Quyền **Read only** trên tài khoản (hoặc qua MCC) | Customer ID dạng `123-456-7890` |
| Amazon Ads | Amazon Advertising Console: **Viewer** | Profile ID |
| Amazon Seller Central | **User permissions**: View cho Orders, Payments, Reports | Seller ID |

## 3. Cấu hình đồng bộ

- Bảng và trường: đúng tên ở spec 01 §8.1 (`<source>__ad_insights_daily` với `date`, `account_id`, `campaign_id`, `campaign_name`, `adgroup_id`, `adgroup_name`, `spend`, `currency`, `impressions`, `clicks`, `conversions`, `conversion_value`).
- Lịch: 3 giờ cho gói Agency, 6 giờ cho gói Seller.
- Nếu Windsor không cho đặt tên bảng: để Windsor ghi vào `t_<id>_windsor`, `ops/bootstrap_tenant.py` sẽ tạo view đúng hợp đồng trong `t_<id>_raw`.

Ghi vào `tenants/<id>.yml`:

```yaml
sources:
  - type: meta_ads
    connector: windsor
    account_id: act_500001
```

Checklist chi tiết: `ops/runbooks/windsor-setup.md`.

## 4. Kiểm tra

- Màn vận hành hiện thời điểm đồng bộ gần nhất của từng bảng Windsor.
- Quá `freshness_hours` mà không có dữ liệu mới → `sync.failed` với `windsor_stale`.
