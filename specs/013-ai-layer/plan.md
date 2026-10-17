# Implementation Plan: Lớp AI

**Branch**: `013-ai-layer` | **Spec**: [spec.md](spec.md)

- `libs/dx_common/src/dx_common/ai_tools.py`: định nghĩa ba công cụ, lọc tham số, cắt 200 dòng.
- `services/mcp/dx_mcp/{server,tools}.py`: MCP server (SDK chính thức, streamable HTTP), gọi lại API bằng token phiên.
- `services/api/app/auth/context.py`: ký/đọc token phiên, `get_metrics_ctx` cho `/v1/metrics*`.
- `services/api/app/ask/`: `guard`, `prompt`, `model` (model và công cụ), `engine` (`ask()`), `render`, `agents`.
- Router `ask.py` (`/v1/ask`, phản hồi, `/v1/ops/metric-requests`); Telegram `messages/ask`; bot gửi tin tự do, `/ask`, nút chọn shop.
- `knowledge/playbooks/{seller,agency}.md`; `ai/evals/*.yaml`, `ai/run_evals.py`; `agents/*/SKILL.md`; workflow `review-change.yml`.
- Web: `/app/ask`, `/ops/metric-requests`, thẻ "Bản nháp AI" ở `/ops/reports/[id]`.

Quyết định: ADR 0002 #47–#54.
