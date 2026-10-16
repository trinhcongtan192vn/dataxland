# ADR – Quyết định kiến trúc

Ghi lại mâu thuẫn giữa các tài liệu gốc, chỗ tài liệu gốc không nói rõ mà việc cài đặt buộc phải chọn, và các lần nâng phiên bản lớn của công cụ (00 §2).

- Tên file: `NNNN-<slug>.md`, đánh số tăng dần từ `0001`.
- Trạng thái: `Proposed` → `Accepted` | `Rejected` | `Superseded by NNNN`.
- Chỉ chủ dự án chuyển ADR sang `Accepted`. Việc bị chặn bởi ADR `Proposed` thì dừng lại.

## Mẫu

```markdown
# NNNN – <Tiêu đề>

- Trạng thái: Proposed
- Ngày: YYYY-MM-DD
- Feature: NNN-<slug>

## Bối cảnh
Trích nguyên văn các đoạn mâu thuẫn hoặc thiếu, kèm vị trí (file, mục).

## Các lựa chọn
1. ...
2. ...

## Quyết định
(Chủ dự án điền.)

## Hệ quả
```
