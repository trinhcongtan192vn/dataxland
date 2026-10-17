---
name: incident-triage
description: Phân tích lần chạy pipeline lỗi hoặc bị chặn của một khách DataxLand và đề xuất cách sửa. Chạy tự động trong worker của API khi có test.failed hoặc sync.failed.
---

# Agent `incident-triage` (spec 09 §8)

Cài trong `services/api/app/ask/agents.py` (`incident_triage`), chạy mỗi vòng worker cho `pipeline_runs` có trạng thái
`failed` hoặc `blocked` trong 2 ngày gần nhất và chưa có `triage_md`. Không có `ANTHROPIC_API_KEY` thì bỏ qua.

## Đầu vào

- Lần chạy: job, bước lỗi, trạng thái từng bước.
- Test chặn: tên test và số dòng lỗi. Dòng dữ liệu lỗi bị bỏ (có thể chứa giá trị gốc).
- Trạng thái nguồn của khách: trạng thái lần gần nhất, mã lỗi, lần thành công gần nhất.

## Các bước

1. Xác định tầng lỗi: nạp nguồn (dlt, Windsor), dbt (staging, core, marts), test, Cube.
2. Đối chiếu mã lỗi nguồn (`AUTH_EXPIRED`, `RATE_LIMITED`, `SCHEMA_CHANGED`) hoặc tên test với nguyên nhân thường gặp.
3. Viết: nguyên nhân khả nghi, các bước kiểm tra, cách sửa đề xuất (Markdown, ≤ 1.500 ký tự).
4. Gọi công cụ `triage`.

## Đầu ra và nơi ghi

`pipeline_runs.triage_md`, hiện ở `/ops/tenants/[id]` trong lịch sử chạy.

## Người duyệt

Engineer trực đọc và quyết định; agent không chạy lại pipeline hay sửa gì.
