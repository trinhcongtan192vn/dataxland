# Feature Specification: Hãng vận chuyển

**Feature Branch**: `015-carriers`
**Created**: 2026-10-17
**Status**: Implemented
**Input**: PRD FR-ING-09, `docs/specs/01-ingestion.md` §9, ADR 0005 (chủ dự án chọn phạm vi)

## User Scenarios & Testing

### US1 – GHN, GHTK qua webhook và API (P2, FR-ING-09)

Chủ shop dán URL webhook vào trang khách hàng của hãng; DataxLand nhận mã vận đơn, gọi API chi tiết lấy phí vận chuyển, phí hoàn, COD.

### US2 – J&T qua file đối soát (P2, FR-ING-09)

Chủ shop tải file đối soát J&T ở `/app/inputs/carriers`; lần chạy kế tiếp nạp vận đơn.

### US3 – Phí và COD theo vận đơn (P2)

Chỉ số `carrier_fees`, `cod_amount`, `shipment_count` theo hãng, trạng thái, ngày gửi; không có thông tin người nhận.

## Requirements

01 §9; ADR 0005. Không thêm yêu cầu ngoài phạm vi đã chốt.
