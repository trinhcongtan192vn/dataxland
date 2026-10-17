---
name: weekly-insight
description: Viết bản nháp nhận định và việc cần làm cho báo cáo tuần của một khách DataxLand, chỉ từ số trong snapshot. Chạy tự động trong worker của API sau khi báo cáo được dựng; data lead duyệt.
---

# Agent `weekly-insight` (spec 09 §8, FR-REP-04)

Cài trong `services/api/app/ask/agents.py` (`weekly_insight`), chạy mỗi vòng worker (`app/jobs.py`) cho báo cáo
`draft` chưa có bản nháp AI. Không có `ANTHROPIC_API_KEY` thì bỏ qua.

## Đầu vào

- `reports.snapshot` (số tổng hợp đã khóa), kỳ báo cáo, cờ dữ liệu cũ.
- `knowledge/playbooks/<gói>.md`.
- 10 quyết định gần nhất trong nhật ký quyết định.
- Ba công cụ chỉ đọc (`list_metrics`, `describe_metric`, `query_metric`) để tra định nghĩa.

Không có dữ liệu người mua trong đầu vào.

## Các bước

1. Đọc snapshot: ba số chính, so với tuần trước và trung bình 4 tuần, cảnh báo.
2. Chọn 3–5 ý quan trọng nhất theo playbook; mỗi ý dẫn số trong snapshot.
3. Nhắc quyết định đến hạn đo lại.
4. Viết tối đa 5 việc cần làm, mỗi việc một dòng.
5. Gọi công cụ `insight_draft`.

## Đầu ra và nơi ghi

`reports.insight_draft_md` (≤ 2.000 ký tự), `reports.actions_draft` (≤ 5). Màn `/ops/reports/[id]` hiện "Bản nháp AI"
và nút "Dùng bản nháp". Dựng lại báo cáo thì bản nháp được làm mới.

## Người duyệt

Data lead. Báo cáo chỉ gửi sau khi data lead điền nhận định chính thức và bấm duyệt.
