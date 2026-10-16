# Connector Shopee

- API: Shopee Open Platform **v2** (`/api/v2/...`), đối chiếu tài liệu ngày 2026-10-17.
- Ký request: `HMAC-SHA256(partner_key, partner_id + path + timestamp + access_token + shop_id)`; API công khai (auth) bỏ `access_token`, `shop_id`.
- Token gian hàng hết hạn sau 4 giờ, refresh token 365 ngày; làm mới qua `/api/v2/auth/access_token/get`.
- Giới hạn: `get_order_list` tối đa 15 ngày mỗi lần (connector dùng cửa sổ 7 ngày), 100 đơn mỗi trang; `get_order_detail` 50 đơn mỗi lần.

| Bảng raw | Endpoint |
|---|---|
| `shopee__orders`, `shopee__order_items` | `order/get_order_list` (theo `update_time`) → `order/get_order_detail`; voucher và phí ship người mua trả lấy từ `payment/get_escrow_detail` |
| `shopee__escrow` | `payment/get_escrow_detail` cho đơn `COMPLETED`; `escrow_release_time` lấy `update_time` của đơn khi API không trả |
| `shopee__returns` | `returns/get_return_list` (theo `update_time`) |
| `shopee__products` | `product/get_item_list` → `get_item_base_info` → `get_model_list` |
| `shopee__daily_totals` | Đếm `order/get_order_list` theo `create_time` từng ngày (đường độc lập với chi tiết đơn). `gross_amount` để trống vì API danh sách không trả tiền; test đối soát chỉ so số đơn (ADR 0002 #23) |

Test: `tests/test_source.py` với Shopee giả lập (`tests/fake_shopee.py`, respx).
