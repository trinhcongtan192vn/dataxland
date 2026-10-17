# Connector Lazada

- API: Lazada Open Platform (REST, `https://api.lazada.vn/rest`), đối chiếu tài liệu ngày 2026-10-17.
- Ký request: `HMAC-SHA256(app_secret, api_path + (khóa+giá trị theo thứ tự khóa, bỏ sign))`, hex chữ hoa; tham số chung `app_key`, `timestamp` (ms), `sign_method=sha256`, `access_token`.
- Token: access token 7–30 ngày tùy ứng dụng; làm mới qua `https://auth.lazada.com/rest/auth/token/refresh`.
- Mã lỗi: `IllegalAccessToken`/`MissingAccessToken` → làm mới token; `ApiCallLimit`/`AppCallLimit` → chờ và thử lại.

| Bảng raw | Endpoint |
|---|---|
| `lazada__orders` | `/orders/get` theo `update_after`/`update_before` (cửa sổ 7 ngày, 100 đơn mỗi trang); đơn mở 30 ngày quét lại qua `/order/get`. `statuses` (mảng) lưu phần tử đầu; địa chỉ ghép từ `address_shipping` |
| `lazada__order_items` | `/orders/items/get` với `order_ids` (tối đa 50) |
| `lazada__transactions` | `/finance/transaction/details/get` theo ngày giao dịch, luôn lấy lại 30 ngày |
| `lazada__returns` | `/reverse/getreverseordersforseller`, mỗi dòng hoàn một bản ghi |
| `lazada__products` | `/products/get` (`filter=all`) |
| `lazada__daily_totals` | `/orders/get` theo `created_after`/`created_before` từng ngày, cộng `price` của danh sách |

Test: `tests/test_source.py` với Lazada giả lập (`tests/fake_lazada.py`, respx).
