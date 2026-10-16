# Spec 10 – Ghép định danh (giai đoạn 2)

Hệ thống: S3. Yêu cầu: FR-ID-01, FR-ID-02, NFR-03.

Phạm vi: ghép sản phẩm xuyên kênh và gộp hồ sơ người mua, hàng chờ duyệt, ghi bảng `identity_map`, áp vào mô hình chung. Giai đoạn 1 đã ghép sản phẩm theo `seller_sku` trùng (spec 02 mục 4); spec này mở rộng cách đó.

Nguyên tắc: quy tắc chắc chắn được duyệt tự động; gợi ý từ độ giống tên và AI luôn qua người duyệt. Dữ liệu người mua không bao giờ được gửi cho AI.

---

## 1. Thành phần

```
services/identity_worker/
  worker.py           # chạy theo khách
  candidates.py       # lấy ứng viên từ stg
  rules.py            # ghép theo quy tắc
  similarity.py       # chặn khối và chấm điểm độ giống
  judge.py            # Claude so từng cặp sản phẩm
  writer.py           # ghi identity_map, gán canonical_id
```

- Chạy như job Dagster `identity_resolution` theo khách: sau `transform.finished`, tối đa một lần mỗi ngày, và khi data lead bấm chạy lại.
- Chỉ chạy cho khách có `features.identity: true` hoặc có hơn một kênh bán.
- Dùng tài khoản dịch vụ của khách để đọc `t_<id>_stg` và ghi `t_<id>_core.identity_map`.

## 2. Ứng viên

| Thực thể | Từ | Trường dùng để ghép |
|---|---|---|
| `product` | `stg_*__products`, `seller_sku` trong `stg_*__order_lines` | `source`, `source_id`, `seller_sku`, `name`, `barcode`, `category_raw`, giá bán trung vị 30 ngày |
| `customer` | `stg_*__orders` | `source`, `buyer_ref`, `buyer_phone_hash`, `buyer_email_hash` |

Chỉ lấy bản ghi chưa có trong `identity_map` hoặc có dữ liệu đổi từ lần chạy trước.

## 3. Ghép theo quy tắc (tự duyệt)

| Thực thể | Quy tắc | `method` |
|---|---|---|
| product | `barcode` trùng (bỏ khoảng trắng, đủ 8–14 chữ số) | `rule_barcode` |
| product | `seller_sku` chuẩn hóa trùng (chữ thường, bỏ khoảng trắng và ký tự `-_.`) | `rule_sku` |
| customer | `phone_hash` trùng | `rule_phone` |
| customer | `email_hash` trùng | `rule_email` |
| customer | Cùng `source` và `buyer_ref` | `rule_buyer_ref` |

Cặp ghép theo quy tắc có `status = approved`, `approved_by = 'system'`.

Người mua chỉ được ghép bằng quy tắc; không có bước gợi ý cho người mua (FR-ID-02).

## 4. Ghép gợi ý cho sản phẩm (FR-ID-01)

1. **Chặn khối:** chỉ so các cặp khác kênh, cùng khoảng giá (lệch ≤ 50%), và có ít nhất một từ khóa chung sau khi chuẩn hóa tên (bỏ dấu, chữ thường, bỏ từ dừng như "chính hãng", "freeship", "sale", kích thước gói). Mỗi sản phẩm lấy tối đa 5 ứng viên tốt nhất.
2. **Điểm độ giống** `sim_score` (0–1): trung bình có trọng số của `token_set_ratio` tên (0,6), trùng thuộc tính trích được như dung tích, khối lượng, màu, kích cỡ (0,3), lệch giá (0,1). Dùng `rapidfuzz`.
3. **Claude so cặp** (với `sim_score ≥ 0,5`): gửi tên, danh mục, thuộc tính, giá của hai sản phẩm; nhận `{same: bool, confidence: 0–1, reason_vi}`. Model `ANTHROPIC_MODEL_AGENT`, nhiệt độ 0, gộp tối đa 20 cặp mỗi lần gọi.
4. **Điểm cuối** `score = 0,4 × sim_score + 0,6 × confidence` (nếu `same = false` thì `score = min(score, 0,3)`).
5. **Phân loại** theo ngưỡng trong cấu hình khách (`identity.suggest_threshold`, mặc định 0,7):
   - `score ≥ suggest_threshold` → `status = proposed`, phát `match.proposed`.
   - Thấp hơn → bỏ qua, không ghi.

Gợi ý không bao giờ tự duyệt, dù điểm cao.

## 5. Hàng chờ duyệt

### 5.1 Dữ liệu (Postgres)

`identity_matches`: `id`, `tenant_id`, `entity`, `left` jsonb (`source`, `source_id`, `label`, thuộc tính hiển thị), `right` jsonb, `method`, `score`, `reason_vi`, `status` (`proposed`, `approved`, `rejected`, `undone`), `decided_by`, `decided_at`, `run_id`.

`label` của sản phẩm là tên và SKU. Với người mua (chỉ quy tắc, không vào hàng chờ) không lưu nhãn.

### 5.2 Giao diện và endpoint

- `/ops/tenants/[id]/matches` (data lead): bảng cặp `proposed`, hai sản phẩm cạnh nhau với tên, SKU, giá, kênh, điểm và lý do; nút Duyệt, Từ chối; duyệt hàng loạt các cặp đã chọn.
- Cột "Cặp ghép chờ duyệt" trên `/ops` (FR-OPS-04) đếm số `proposed`.

| Method | Đường dẫn | Quyền |
|---|---|---|
| `GET` | `/v1/identity/matches?status=proposed` | `ops.read` |
| `POST` | `/v1/identity/matches/{id}/approve` | `ops.write` |
| `POST` | `/v1/identity/matches/{id}/reject` | `ops.write` |
| `POST` | `/v1/identity/matches/bulk` | `ops.write`, `{ids[], action}` |
| `POST` | `/v1/identity/matches/{id}/undo` | `ops.write`; gỡ một cặp đã duyệt |

Mọi quyết định ghi `audit_log` và được giữ để đo lại ngưỡng (tỷ lệ duyệt theo khoảng điểm).

## 6. Ghi kết quả

`writer.py` sau mỗi lần chạy và sau mỗi quyết định duyệt:

1. Lấy mọi cặp `approved` của khách, dựng các nhóm liên thông (union-find) cho từng thực thể.
2. `canonical_id` của nhóm: với sản phẩm là `product_id` (spec 02) của thành viên có doanh thu 90 ngày lớn nhất; với người mua là khóa băm của thành viên có đơn sớm nhất. Giữ ổn định giữa các lần chạy: nhóm đã có `canonical_id` thì giữ nguyên trừ khi bị tách.
3. Ghi đè `t_<id>_core.identity_map(entity, source, source_id, canonical_id, method, approved_by, approved_at)`.
4. Phát sự kiện nội bộ để Dagster chạy lại `dbt build` cho các model chịu ảnh hưởng.

## 7. Áp vào mô hình chung

- Model `int_identity__product` và `int_identity__customer` trong `transform/models/core/` đọc `identity_map` (khai báo là source, có thể trống).
- `dim_product.product_id` = `canonical_id` nếu có, nếu không thì khóa của giai đoạn 1. Tương tự `dim_customer.customer_id`.
- `dim_customer` có thêm `first_order_at`, `first_channel_id`, `order_count_lifetime` sau khi gộp.
- Khách bật `features.identity: true` thì chỉ số `repeat_customer_rate` được mở (spec 03 mục 4.4).
- Giá vốn nhập theo `seller_sku`: khi nhiều SKU gộp thành một sản phẩm, mỗi SKU vẫn dùng giá vốn của chính nó; sổ tay ghi chú điều này.

## 8. Bảo vệ dữ liệu cá nhân (NFR-03)

- Worker chỉ đọc cột băm của người mua từ `stg`, không đọc cột gốc.
- `identity_map` của người mua chỉ chứa `source`, `source_id` (mã đơn hoặc `buyer_ref`) và `canonical_id` dạng băm.
- `judge.py` chỉ nhận dữ liệu sản phẩm. Test kiểm tra payload gửi cho model không có trường của người mua.
- `ops/erase_subject.py` (spec 04 mục 8) xóa thêm các dòng `identity_map` của người đó.

## 9. Kiểm thử

| Test | Nội dung | FR |
|---|---|---|
| `test_fr_id_01_rule_barcode_auto_approved` | Hai sản phẩm cùng mã vạch được duyệt tự động | FR-ID-01 |
| `test_fr_id_01_suggestion_needs_review` | Cặp tên gần giống vào hàng chờ, chưa có trong `identity_map` cho đến khi duyệt | FR-ID-01 |
| `test_fr_id_01_undo_splits_group` | Gỡ một cặp tách nhóm, `canonical_id` cũ giữ cho nhóm lớn hơn | FR-ID-01 |
| `test_fr_id_02_customer_merge_by_phone_hash` | Hai đơn khác sàn cùng `phone_hash` có cùng `customer_id` sau khi dbt chạy lại | FR-ID-02 |
| `test_nfr_03_judge_payload_has_no_buyer_data` | Payload gửi model chỉ có trường sản phẩm | NFR-03 |
| `test_canonical_id_stable` | Chạy hai lần không đổi `canonical_id` | |

Dữ liệu mẫu cần thêm: cùng một sản phẩm bán trên Shopee và TikTok Shop với tên khác nhau và SKU khác nhau; một người mua đặt trên hai sàn với cùng số điện thoại (giả).

## 10. Tiêu chí hoàn thành

- Trên `demo_seller`, worker sinh cặp gợi ý đúng cho sản phẩm mẫu; duyệt xong thì dashboard lãi theo SKU gộp hai dòng thành một.
- `repeat_customer_rate` có giá trị khi bật `features.identity`.
- Mọi test ở mục 9 qua.
