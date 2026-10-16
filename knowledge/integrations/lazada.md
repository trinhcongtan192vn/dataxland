# Lazada Open Platform

Connector Lazada thuộc mốc M4 (spec 01 §5). Luồng kết nối OAuth đã có; connector nạp dữ liệu được bật ở bước 011.

| Lớp | Lưu ở đâu |
|---|---|
| Ứng dụng của DataxLand (`app_key`, `app_secret`) | Secret `dx-lazada-app` |
| Token của seller | Secret `dx-<tenant_id>-lazada-<seller_id>` |

## 1. Tạo ứng dụng

1. Đăng ký tại **open.lazada.com** (tài khoản nhà phát triển, loại ISV), xác minh doanh nghiệp.
2. **App Console → Create App**, loại **ERP/Seller In-house**; chọn quốc gia **Vietnam**.
3. **Callback URL**: `<MARKETPLACE_OAUTH_REDIRECT_BASE>/v1/connect/lazada/callback`.
4. Xin quyền API: Order, Finance, Product, Reverse (trả hàng).
5. Lấy **App Key**, **App Secret** ở trang tổng quan của ứng dụng.

## 2. Ghi khóa

`.secrets/dx-lazada-app` (local) hoặc Secret Manager (dev/prod):

```json
{"app_key": "<app key>", "app_secret": "<app secret>"}
```

## 3. Kết nối seller

**Vận hành → Khách → <khách> → Lazada → Kết nối**. Seller đăng nhập Lazada Seller Center (Việt Nam), bấm **Submit**. API ghi token và `seller_id`, rồi thêm nguồn vào `tenants/<id>.yml` như Shopee.

Access token Lazada hết hạn sau 7–30 ngày tùy loại ứng dụng; hệ thống làm mới tự động bằng refresh token.
