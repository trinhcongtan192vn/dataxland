# Shopee Open Platform

DataxLand đọc đơn hàng, quyết toán, trả hàng và sản phẩm của gian hàng qua Shopee Open Platform API v2 (spec 01 §3). Có hai lớp khóa:

| Lớp | Ai cấp | Lưu ở đâu |
|---|---|---|
| Ứng dụng đối tác của DataxLand (`partner_id`, `partner_key`) | Shopee, một lần cho DataxLand | Secret `dx-shopee-app` |
| Token của từng gian hàng (`access_token`, `refresh_token`) | Chủ shop bấm đồng ý trên Shopee | Secret `dx-<tenant_id>-shopee-<shop_id>`, do API tự ghi sau khi kết nối |

## 1. Tạo ứng dụng đối tác (làm một lần)

1. Đăng ký tài khoản tại **open.shopee.com** bằng email công ty, chọn loại nhà phát triển **Third-party Partner Platform (ISV)**.
2. Hoàn tất xác minh doanh nghiệp (giấy phép kinh doanh, người đại diện). Shopee duyệt trong vài ngày làm việc.
3. Vào **App Management → Create App**:
   - App type: **ERP System** (cần quyền đơn hàng, thanh toán, sản phẩm, trả hàng).
   - Redirect URL domain: tên miền công khai của API, ví dụ `api.dataxland.vn`.
4. Sau khi tạo, mở ứng dụng để lấy:
   - **Partner ID** (Live) → `partner_id`
   - **Partner Key** (Live) → `partner_key`
   - Muốn thử trước: dùng cặp **Test Partner ID / Test Key** và thêm `"api_base": "https://partner.test-stable.shopeemobile.com"`.
5. Bật các nhóm API: Order, Payment, Returns, Product, Shop.

## 2. Ghi khóa ứng dụng

Không dán khóa vào code, file `.env` dùng chung hay `tenants/*.yml`.

- `local`: tạo file `.secrets/dx-shopee-app` với nội dung:

  ```json
  {"partner_id": 2001234, "partner_key": "<partner key>"}
  ```

- `dev`/`prod`:

  ```bash
  printf '%s' '{"partner_id": 2001234, "partner_key": "<partner key>"}' | \
    gcloud secrets create dx-shopee-app --data-file=- --project "$GCP_PROJECT_ID"
  # đã có secret: gcloud secrets versions add dx-shopee-app --data-file=-
  ```

Biến môi trường `MARKETPLACE_OAUTH_REDIRECT_BASE` phải là URL công khai của API (ví dụ `https://api.dataxland.vn`). Callback là `<MARKETPLACE_OAUTH_REDIRECT_BASE>/v1/connect/shopee/callback`.

## 3. Kết nối gian hàng của khách

1. Vào **Vận hành → Khách → <khách>**, ở dòng nguồn Shopee bấm **Kết nối**.
2. Gửi đường dẫn cho chủ shop (hoặc ngồi cùng chủ shop): đăng nhập Shopee Seller bằng tài khoản **chủ shop** (không dùng tài khoản phụ), bấm **Authorize**.
3. Shopee chuyển về cổng với thông báo đã kết nối, kèm `shop_id` và tên secret.
4. Thêm vào `tenants/<tenant_id>.yml`:

   ```yaml
   sources:
     - type: shopee
       connector: dlt
       account_id: "<shop_id>"
       secret_ref: dx-<tenant_id>-shopee-<shop_id>
   ```

5. Commit, chạy `make sync-tenants` (hoặc chờ CI), rồi bấm **Chạy lại** ở màn hình vận hành.

## 4. Kiểm tra

- Màn này hiện **Đã cấu hình** cho `dx-shopee-app` và secret của shop.
- Lần chạy đầu nạp 90 ngày; bảng `t_<id>_raw.shopee__orders` có dữ liệu.
- So số đơn và doanh thu 30 ngày với Seller Centre, lệch dưới 1% (FR-ING-01).

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `APP_NOT_CONFIGURED` khi bấm Kết nối | Chưa có secret `dx-shopee-app` | Làm mục 2 |
| Shopee báo `error_param` / redirect không khớp | Tên miền redirect trong ứng dụng khác `MARKETPLACE_OAUTH_REDIRECT_BASE` | Sửa một trong hai cho khớp |
| `sync.failed` với `auth_revoked` | Shop thu hồi quyền hoặc refresh token hết hạn (365 ngày) | Kết nối lại theo mục 3 |
| `rate_limited` | Vượt giới hạn gọi API | Hệ thống tự thử lại; nếu lặp lại, giãn lịch đồng bộ |

Token gian hàng hết hạn sau 4 giờ và được làm mới tự động trước mỗi lần chạy. Runbook: `ops/runbooks/marketplace-oauth.md`.
