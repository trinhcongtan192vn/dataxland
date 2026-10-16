# TikTok Shop Partner Center

DataxLand đọc đơn hàng, quyết toán, trả hàng và sản phẩm qua TikTok Shop Partner API phiên bản `202309` (spec 01 §4).

| Lớp | Ai cấp | Lưu ở đâu |
|---|---|---|
| Ứng dụng của DataxLand (`app_key`, `app_secret`, `service_id`) | TikTok Shop, một lần | Secret `dx-tiktok_shop-app` |
| Token của từng shop (`access_token`, `refresh_token`, `shop_cipher`) | Chủ shop bấm đồng ý | Secret `dx-<tenant_id>-tiktok_shop-<shop_id>`, do API tự ghi |

## 1. Tạo ứng dụng (làm một lần)

1. Đăng ký tại **partner.tiktokshop.com** với vai trò **App developer**, chọn thị trường **Vietnam**, xác minh doanh nghiệp.
2. **App & Service → Create app**, loại **Custom app** (dùng cho khách của mình) hoặc **Public app** nếu muốn lên chợ ứng dụng.
3. Trong mục **Manage API**, xin quyền (scope): Order Information, Finance Information, Return & Refund, Product Basic, Shop Authorized Information.
4. Mục **Redirect URL**: nhập `<MARKETPLACE_OAUTH_REDIRECT_BASE>/v1/connect/tiktok_shop/callback`.
5. Ở trang **Basic information** của ứng dụng lấy **App key**, **App secret**, và **Service ID** (dùng cho đường dẫn cấp quyền).

## 2. Ghi khóa ứng dụng

- `local`: `.secrets/dx-tiktok_shop-app`

  ```json
  {"app_key": "<app key>", "app_secret": "<app secret>", "service_id": "<service id>"}
  ```

- `dev`/`prod`: `gcloud secrets create dx-tiktok_shop-app --data-file=-` với cùng JSON.

## 3. Kết nối shop của khách

1. **Vận hành → Khách → <khách>**, dòng TikTok Shop bấm **Kết nối**.
2. Chủ shop đăng nhập TikTok Shop Seller Center (tài khoản chủ), chọn shop Việt Nam, bấm **Authorize**.
3. API đổi mã lấy token, gọi `Get Authorized Shops` để lấy `shop_id` và `shop_cipher`, ghi secret và chuyển về cổng.
4. Thêm nguồn vào `tenants/<tenant_id>.yml` với `account_id: "<shop_id>"`, `secret_ref: dx-<tenant_id>-tiktok_shop-<shop_id>`.

Nếu một tài khoản có nhiều shop, hệ thống lấy shop đầu tiên và ghi các shop còn lại vào nhật ký kiểm toán; muốn nạp shop khác, kết nối lại bằng tài khoản của shop đó.

## 4. Kiểm tra

- Lần chạy đầu nạp 90 ngày vào `t_<id>_raw.tiktok_shop__*`.
- Số đơn và doanh thu 30 ngày khớp Seller Center trong 1% (FR-ING-02).

## Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `EXCHANGE_FAILED` sau khi chủ shop đồng ý | Kiểm tra Redirect URL trong ứng dụng khớp đúng callback; kiểm tra `app_secret` |
| `auth_revoked` | Refresh token hết hạn hoặc shop gỡ ứng dụng: kết nối lại |
| Thiếu quyết toán | Ứng dụng chưa được duyệt scope Finance: xin thêm ở Manage API |
