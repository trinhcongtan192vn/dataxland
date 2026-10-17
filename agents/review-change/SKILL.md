---
name: review-change
description: Rà một PR của DataxLand theo quy tắc trong CLAUDE.md và liệt kê chỉ số, khách bị ảnh hưởng (từ manifest dbt). Chạy trên mỗi PR qua GitHub Action, bình luận vào PR.
---

# Agent `review-change` (spec 09 §8)

## Đầu vào

- Diff của PR (`git diff origin/main...HEAD`).
- `transform/target/manifest.json` (sau `dbt parse`), `semantic/dist/metrics.json`, `tenants/*.yml`.

## Các bước

1. Đọc `CLAUDE.md` mục "Quy tắc không được vi phạm" và "Quy ước code".
2. Với từng file đổi, kiểm tra:
   - Tách biệt khách: endpoint không lấy `tenant_id` từ tham số; không SQL nào đọc dataset của hai khách.
   - Một định nghĩa chỉ số: không tính chỉ số bằng SQL riêng ở API, web, bot, báo cáo.
   - Không sửa tay `semantic/cube/`, `semantic/dist/`; đổi công thức chỉ số thì tăng `version`.
   - SQL ở `core`, `marts` dùng macro cross-db; hàm riêng BigQuery chỉ ở `staging`.
   - Thông tin người mua chỉ ở `raw`, `stg`; không API, bot, log nào trả hoặc ghi.
   - Không có bí mật trong code hay `tenants/*.yml`.
   - AI đề xuất, người duyệt: không luồng nào để AI tự gửi cho khách hay tự gộp định danh.
   - Model dbt đổi thì có test và dữ liệu mẫu; tên test có mã yêu cầu.
3. Từ `manifest.json`: model đổi → model con → cube trong `semantic/dist/metrics.json` → chỉ số bị ảnh hưởng;
   khách bị ảnh hưởng là khách có gói và nguồn dùng các model đó.
4. Viết một bình luận: vi phạm (file:dòng, quy tắc, gợi ý sửa), chỉ số và khách bị ảnh hưởng. Không có vi phạm thì nói
   rõ.

## Đầu ra và nơi ghi

Một bình luận trên PR (`.github/workflows/review-change.yml`). Agent chỉ đọc; không đẩy commit.

## Người duyệt

Người review PR quyết định; bình luận của agent không chặn merge.
