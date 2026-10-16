# Connector TikTok Shop

- API: TikTok Shop Partner API phiên bản **202309**, đối chiếu tài liệu ngày 2026-10-17.
- Ký request: `HMAC-SHA256(app_secret, app_secret + path + (khóa+giá trị theo thứ tự khóa, bỏ sign, access_token) + body + app_secret)`; token ở header `x-tts-access-token`; `shop_cipher` trong query.
- Token làm mới qua `https://auth.tiktok-shops.com/api/v2/token/refresh`.

| Bảng raw | Endpoint |
|---|---|
| `tiktok_shop__orders`, `tiktok_shop__order_items` | `POST /order/202309/orders/search` (theo `update_time`), đơn mở cần quét lại qua `GET /order/202309/orders?ids=` |
| `tiktok_shop__settlements` | `GET /finance/202309/orders/{order_id}/statement_transactions` cho đơn `COMPLETED` |
| `tiktok_shop__returns` | `POST /return_refund/202309/returns/search` |
| `tiktok_shop__products` | `POST /product/202309/products/search` → `GET /product/202309/products/{id}` |
| `tiktok_shop__daily_totals` | `orders/search` theo `create_time` từng ngày, cộng `original_total_product_price` từ danh sách |

Test: `tests/test_source.py` với TikTok Shop giả lập (`tests/fake_tiktok.py`, respx).
