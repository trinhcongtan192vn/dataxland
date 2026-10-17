# Feature Specification: Ngân sách theo chiến dịch, chi phí theo khách

**Feature Branch**: `014-campaign-budgets-costs`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: `docs/specs/05-api-and-auth.md` §6.5 (FR-INP-05), `04-ops-and-orchestration.md` §6–§7 (FR-OPS-06), `06-portal.md` §10

## User Scenarios & Testing

### US1 – Ngân sách theo chiến dịch (P2, FR-INP-05)

Khách nhập ngân sách tháng cho từng chiến dịch ở `/app/inputs/budgets`; tiến độ ngân sách cắt được theo chiến dịch; tổng theo nền tảng không đổi.

### US2 – Chi phí và giờ người theo khách (P2, FR-OPS-06)

Màn `/ops/costs` hiện chi phí GCP (billing export theo nhãn `tenant_id`), Windsor và Claude chia theo khách, giờ người nhập tay; `/ops` hiện tổng tháng.

## Requirements

05 §6.5; 04 §6–§7; 06 §10. Không thêm yêu cầu.
