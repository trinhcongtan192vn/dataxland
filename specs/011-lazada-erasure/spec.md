# Feature Specification: Lazada, xóa dữ liệu người mua

**Feature Branch**: `011-lazada-erasure`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/README.md` bước 11 (M4) → `01-ingestion.md` §5, `04-ops-and-orchestration.md` §8, `08-telegram-bot.md` §3.6, §6

## User Scenarios & Testing

### US1 – Nạp Lazada (P1, FR-ING-03)

Connector Lazada nạp đơn, dòng đơn, giao dịch, hoàn hàng, sản phẩm, tổng theo ngày; cùng hành vi bắt buộc của spec 01 §2.1.

### US2 – Xóa dữ liệu một người mua (P1, FR-OPS-09)

`ops/erase_subject.py` tìm theo điện thoại, email hoặc mã người mua; xóa trường cá nhân ở raw (giữ đơn), chạy lại dbt để không còn bản ghi gốc hay băm; ghi `erasure_log`; `--dry-run` chỉ đếm.

### US3 – Nhóm Telegram và giới hạn tần suất (P1, FR-TG-05, FR-TG-07)

Đã cài ở bước 8 (`008-weekly-report-bot`): mã nhóm chỉ owner, phạm vi chỉ số, che số ngoài phạm vi; giới hạn lệnh theo cửa sổ trượt, khóa mã sai.

## Requirements

01 §5; 04 §8; 08 §3.6, §6. Không thêm yêu cầu.
