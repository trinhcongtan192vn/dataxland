<!--
Sync Impact Report
- Version: (template) → 1.0.0
- Nguồn: CLAUDE.md, docs/specs/README.md, docs/specs/00-foundation.md, quy tắc quy trình do chủ dự án đặt (2026-10-16)
- Templates: plan-template.md, spec-template.md, tasks-template.md dùng nguyên bản; mục "Constitution Check" của plan đối chiếu với các nguyên tắc dưới đây
- TODO: không có
-->

# DataxLand Constitution

Hiến pháp này không đặt ra yêu cầu sản phẩm mới. Nó chỉ chép lại các quy tắc bắt buộc đã có trong `CLAUDE.md` và `docs/specs/00-foundation.md`, cùng quy trình spec-kit mà chủ dự án đặt ra. Khi có khác biệt, tài liệu gốc thắng.

## Core Principles

### I. Tài liệu gốc là nguồn sự thật (NON-NEGOTIABLE)

- `docs/specs/*` là nguồn sự thật. Artifact của spec-kit (`specs/NNN-*/spec.md`, `plan.md`, `tasks.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`) chỉ được suy ra từ đó, không thêm yêu cầu, endpoint, bảng, chỉ số hay hành vi mới.
- Mỗi yêu cầu trong artifact phải trỏ về nguồn: mã FR/NFR và mục spec, ví dụ `FR-AUTH-02 (05 §3)`.
- Thứ tự ưu tiên khi mâu thuẫn: spec đang làm > `docs/specs/00-foundation.md` > `docs/prd.md` > `docs/architecture.md`.
- Gặp mâu thuẫn hoặc chỗ tài liệu gốc không nói rõ mà việc cài đặt buộc phải chọn: dừng lại, ghi `docs/adr/NNNN-<slug>.md` (trạng thái `Proposed`), hỏi chủ dự án. Không tự chọn. Chỉ tiếp tục khi ADR đã `Accepted`.
- `[NEEDS CLARIFICATION]` trong spec-kit được giải quyết bằng cách trích tài liệu gốc; nếu tài liệu gốc không trả lời được thì đi theo quy trình ADR ở trên.

### II. Tách biệt khách (NFR-01)

- Mọi endpoint xác định khách bằng quyền của người gọi trong Postgres, không tin `tenant_id` từ tham số.
- Không SQL nào đọc dataset của hai khách cùng lúc.
- Kiểm thử tách biệt khách (00 §9) là bắt buộc trong CI.

### III. Một định nghĩa chỉ số

- Không tính chỉ số bằng SQL riêng ở API, web, bot hay báo cáo. Mọi số đi qua `POST /v1/metrics/query` (Cube).
- Không sửa tay `semantic/cube/` và `semantic/dist/`. Sửa `semantic/metrics/*.yml` rồi chạy `make semantic`.
- Thay đổi công thức chỉ số phải tăng `version` trong YAML của chỉ số đó.

### IV. Dữ liệu cá nhân và bí mật

- Thông tin cá nhân người mua (số điện thoại, email, tên, địa chỉ) chỉ ở dạng gốc trong `raw` và `stg`. Từ `core` trở lên chỉ có dạng băm. Không API, bot hay log nào trả hoặc ghi chúng.
- Không có bí mật trong code hoặc trong `tenants/*.yml`. Dùng `secret_ref` và `dx_common.secrets`. `.secrets/` và `.env` nằm trong `.gitignore`; CI chạy `gitleaks`.
- Dữ liệu test chỉ dùng hai khách giả lập `demo_seller`, `demo_agency`. Không đưa dữ liệu khách thật vào repo.

### V. AI đề xuất, người duyệt

Không luồng nào để AI tự gửi nội dung cho khách hoặc tự gộp định danh mà không qua bước duyệt.

### VI. Kiểm thử theo mã yêu cầu

- Mọi tiêu chí nghiệm thu của các FR liên quan có test tự động; tên test ghi mã yêu cầu, ví dụ `test_fr_rep_05_sends_three_key_numbers`.
- Thay đổi model dbt phải kèm test và dữ liệu mẫu trong `transform/samples/`.

## Ràng buộc kỹ thuật

Theo `docs/specs/00-foundation.md` §2–§4 và `CLAUDE.md`:

- Python 3.12, `uv` workspace, `ruff`, `mypy --strict` cho `libs/` và `services/`. Dùng `dx_common` thay vì tự viết config, log, events, secrets.
- TypeScript strict, Next.js, pnpm. Giao diện tiếng Việt, số tiền dạng `1.234.567 ₫`.
- SQL trong `transform/models/core` và `transform/models/marts` dùng macro cross-db của dbt; hàm riêng của BigQuery chỉ được dùng trong `staging`.
- Timestamp lưu UTC; ngày nghiệp vụ và tuần ISO tính theo `Asia/Ho_Chi_Minh`.
- Code không rẽ nhánh theo `DX_ENV` ngoài việc chọn adapter.
- Nâng phiên bản lớn của công cụ phải có ADR.

## Quy trình phát triển (spec-kit SDD)

- Mỗi bước trong bảng "Thứ tự xây" của `docs/specs/README.md` là một feature spec-kit, làm trên một nhánh riêng tách từ `main`, theo đúng thứ tự:

  | Bước | Nhánh / thư mục `specs/` | Spec gốc |
  |---|---|---|
  | 1 | `001-foundation` | 00 |
  | 2 | `002-control-plane-auth` | 05 |
  | 3 | `003-tenant-registry-orchestration` | 04 |
  | 4 | `004-dbt-transform` | 02 |
  | 5 | `005-semantic-layer` | 03 |
  | 6 | `006-ingestion-connectors` | 01 |
  | 7 | `007-portal-dashboard-inputs` | 06, 05 |
  | 8 | `008-weekly-report-notify-bot` | 06, 04, 08 |
  | 9 | `009-health-check` | 07 |
  | 10 | `010-ops-screen-agency` | 06 |
  | 11 | `011-lazada-erasure-tg-groups` | 01, 04, 08 |

- Phạm vi của một feature chỉ gồm những gì bước đó ghi trong bảng. Phần của spec thuộc bước sau hoặc giai đoạn 2 không được kéo vào sớm.
- Chu trình mỗi feature: `/speckit-specify` → (`/speckit-clarify` nếu cần) → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`.
- Một feature kết thúc khi đạt Định nghĩa hoàn thành (00 §10): đạt "Tiêu chí hoàn thành" của spec tương ứng, có test cho mọi tiêu chí nghiệm thu, CI xanh, không còn `TODO` không có mã issue, tài liệu liên quan đã cập nhật. Sau đó mới merge vào `main` và mở nhánh kế tiếp.

## Governance

- Hiến pháp này đứng dưới tài liệu gốc: nếu nó khác `CLAUDE.md` hoặc `docs/specs/*` thì tài liệu gốc thắng và hiến pháp phải được sửa.
- Mục "Constitution Check" của mỗi `plan.md` phải đối chiếu với các nguyên tắc I–VI.
- Sửa hiến pháp: cập nhật Sync Impact Report, tăng phiên bản theo semver (MAJOR: bỏ hoặc đổi nghĩa nguyên tắc; MINOR: thêm nguyên tắc hoặc mục; PATCH: diễn đạt lại).

**Version**: 1.0.0 | **Ratified**: 2026-10-16 | **Last Amended**: 2026-10-16
