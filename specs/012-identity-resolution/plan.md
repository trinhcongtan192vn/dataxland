# Implementation Plan: Ghép định danh

**Branch**: `012-identity-resolution` | **Spec**: [spec.md](spec.md)

- `services/identity_worker/identity_worker/`: `candidates` (đọc `stg`), `rules`, `similarity` (rapidfuzz + thuộc tính quy cách), `judge` (Claude, lô 20 cặp), `writer` (union-find, `canonical_id` ổn định), `worker` (một lượt chạy).
- API `services/api/app/routers/identity.py`: hàng chờ, duyệt/từ chối/gỡ/hàng loạt, endpoint nội bộ cho worker.
- Pipeline: bước `resolve_identity` trong `dx_pipelines/runner.py`.
- Semantic: kiểu chỉ số `per_entity`, chiều nội bộ `customer`, 3 chỉ số khách hàng; `cogs` ghi chú giá vốn theo SKU.
- Web: `/ops/tenants/[id]/matches`, cột "Cặp ghép chờ duyệt" ở `/ops`.
- `ops/erase_subject.py` xóa dòng `identity_map` của người mua.

Quyết định: ADR 0002 #42–#46.
