# CLAUDE.md – DataxLand

## Dự án là gì

DataxLand giúp một trưởng nhóm data vận hành dữ liệu cho nhiều SME bán đa kênh. Dữ liệu từ sàn (Shopee, TikTok Shop, Lazada) và quảng cáo (Meta, TikTok, Google, Amazon) được chuẩn hóa về một mô hình chung, tính chỉ số qua một thư viện duy nhất (Cube), rồi đưa tới khách qua cổng web và Telegram bot.

## Đọc gì trước khi làm

1. `docs/specs/README.md` – danh sách spec và thứ tự xây
2. `docs/specs/00-foundation.md` – quy ước bắt buộc
3. Spec của phần đang làm
4. `docs/prd.md` và `docs/architecture.md` khi cần bối cảnh

Spec thắng PRD, PRD thắng kiến trúc. Gặp mâu thuẫn thì dừng lại và hỏi, không tự chọn.

## Lệnh thường dùng

```bash
make setup                       # cài đặt
make up                          # bật stack local
make seed-local                  # nạp dữ liệu mẫu cho demo_seller, demo_agency
make dbt-build TENANT=demo_seller
make semantic                    # sinh model Cube, sổ tay, ngữ cảnh AI từ semantic/metrics
make test                        # toàn bộ test
make lint
```

## Quy tắc không được vi phạm

- **Tách biệt khách.** Mọi endpoint xác định khách bằng quyền của người gọi trong Postgres, không tin `tenant_id` từ tham số. Không SQL nào đọc dataset của hai khách cùng lúc.
- **Một định nghĩa chỉ số.** Không tính chỉ số bằng SQL riêng ở API, web, bot hay báo cáo. Mọi số đi qua `POST /v1/metrics/query` (Cube).
- **Không sửa tay** `semantic/cube/` và `semantic/dist/`. Sửa `semantic/metrics/*.yml` rồi chạy `make semantic`.
- **SQL đa nền tảng** trong `transform/models/core` và `transform/models/marts`: dùng macro cross-db của dbt, không dùng hàm riêng của BigQuery. Hàm riêng chỉ được dùng trong `staging`.
- **Thông tin cá nhân người mua** (số điện thoại, email, tên, địa chỉ) chỉ ở dạng gốc trong `raw` và `stg`. Từ `core` trở lên chỉ có dạng băm. Không API, bot hay log nào trả hoặc ghi chúng.
- **Không có bí mật trong code hoặc trong `tenants/*.yml`.** Dùng `secret_ref` và `dx_common.secrets`.
- **AI đề xuất, người duyệt.** Không luồng nào để AI tự gửi nội dung cho khách hoặc tự gộp định danh mà không qua bước duyệt.
- **Dữ liệu test** chỉ dùng hai khách giả lập `demo_seller`, `demo_agency`. Không đưa dữ liệu khách thật vào repo.

## Quy ước code

- Python 3.12, `ruff`, `mypy --strict` cho `libs/` và `services/`. Dùng `dx_common` thay vì tự viết config, log, events, secrets.
- TypeScript strict. Giao diện tiếng Việt, số tiền dạng `1.234.567 ₫`.
- Timestamp lưu UTC; ngày nghiệp vụ và tuần tính theo `Asia/Ho_Chi_Minh`.
- Tên test ghi mã yêu cầu: `test_fr_rep_05_sends_three_key_numbers`.
- Thay đổi model dbt phải kèm test và dữ liệu mẫu trong `transform/samples/`.
- Thay đổi công thức chỉ số phải tăng `version` trong YAML của chỉ số đó.

## Định nghĩa hoàn thành

Xem `docs/specs/00-foundation.md` mục 10.
