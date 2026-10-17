"""Agent nội bộ chạy trong worker của API (spec 09 §8): `weekly-insight` và `incident-triage`.

AI đề xuất, người duyệt: `weekly-insight` chỉ ghi `reports.insight_draft_md` và `reports.actions_draft`; data lead vẫn
phải sửa hoặc chấp nhận rồi bấm duyệt. `incident-triage` ghi `pipeline_runs.triage_md` cho team đọc.
Không gửi dữ liệu người mua cho model: snapshot báo cáo chỉ có số tổng hợp, lỗi pipeline bỏ dòng dữ liệu lỗi.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ask.engine import ToolSession, record_cost, run_model
from app.ask.model import ModelCaller, ToolRunner, cost_usd, default_caller, default_runner
from app.ask.prompt import playbook
from app.auth.context import internal_ctx
from app.db.models import Decision, PipelineRun, Report, SourceSync
from dx_common.config import get_settings
from dx_common.logging import get_logger
from dx_common.timeutil import now_utc

log = get_logger("api.agents")

MAX_INSIGHT = 2000
MAX_ACTIONS = 5

INSIGHT_TOOL: dict[str, Any] = {
    "name": "insight_draft",
    "description": "Gửi bản nháp nhận định tuần và việc cần làm.",
    "input_schema": {
        "type": "object",
        "properties": {
            "insight_md": {"type": "string", "description": "Nhận định tiếng Việt, tối đa 2.000 ký tự"},
            "actions": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_ACTIONS},
        },
        "required": ["insight_md", "actions"],
    },
}

TRIAGE_TOOL: dict[str, Any] = {
    "name": "triage",
    "description": "Gửi phân tích sự cố.",
    "input_schema": {
        "type": "object",
        "properties": {"triage_md": {"type": "string"}},
        "required": ["triage_md"],
    },
}

INSIGHT_SYSTEM = """Bạn là chuyên viên dữ liệu của DataxLand, viết bản NHÁP nhận định cho báo cáo tuần của một khách.
Data lead sẽ đọc, sửa rồi mới duyệt; bản nháp không bao giờ tự gửi cho khách.

Quy tắc:
- Chỉ dùng số có trong `snapshot` (số tổng hợp đã khóa của báo cáo). Không bịa số, không tự tính chỉ số mới ngoài
  phép tính đơn giản giữa các số trong snapshot. Công cụ chỉ dùng để tra định nghĩa chỉ số.
- Nhận định tiếng Việt, tối đa 2.000 ký tự, 3–5 ý: điều gì thay đổi, vì sao (theo số), điều cần chú ý.
  Số tiền dạng 1.234.567 ₫, phần trăm dạng 9,4%.
- Tối đa 5 việc cần làm, mỗi việc một dòng ≤ 300 ký tự, cụ thể và làm được trong tuần tới.
- Xem nhật ký quyết định để nhắc quyết định nào cần đo lại hoặc đã có kết quả.
- Không nêu thông tin người mua.
- Kết thúc bằng công cụ `insight_draft`.
"""

TRIAGE_SYSTEM = """Bạn là kỹ sư dữ liệu của DataxLand. Đọc thông tin một lần chạy pipeline lỗi của một khách và viết
phân tích ngắn (Markdown, tối đa 1.500 ký tự) gồm: nguyên nhân khả nghi, các bước kiểm tra, cách sửa đề xuất.
Pipeline: dlt/Windsor nạp raw → dbt (staging, core, marts, test) → Cube. Lỗi nguồn có mã như AUTH_EXPIRED,
RATE_LIMITED, SCHEMA_CHANGED. Không đoán thông tin người mua. Kết thúc bằng công cụ `triage`."""


def _agent_caller(caller: ModelCaller | None) -> ModelCaller | None:
    return caller or default_caller("agent")


def _finish_cost(db: Session, tenant_id: str, sess: ToolSession) -> None:
    usd = cost_usd(get_settings().anthropic_model_agent, sess.input_tokens, sess.output_tokens)
    record_cost(db, tenant_id, usd)


def _decisions(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Decision).where(Decision.tenant_id == tenant_id).order_by(Decision.decided_on.desc()).limit(10)
    )
    out: list[dict[str, Any]] = []
    for d in rows:
        out.append(
            {
                "decided_on": d.decided_on.isoformat(),
                "title": d.title,
                "metric": d.metric,
                "baseline_value": float(d.baseline_value) if isinstance(d.baseline_value, Decimal) else None,
                "target_value": float(d.target_value) if isinstance(d.target_value, Decimal) else None,
                "remeasure_on": d.remeasure_on.isoformat(),
            }
        )
    return out


def weekly_insight(
    db: Session, report: Report, *, caller: ModelCaller | None = None, runner: ToolRunner | None = None
) -> bool:
    """Ghi bản nháp AI cho một báo cáo `draft`. Trả True khi có bản nháp."""
    call = _agent_caller(caller)
    if call is None or report.status != "draft":
        return False
    ctx = internal_ctx(db, report.tenant_id)
    payload = {
        "tenant": ctx.tenant.name,
        "pack": report.pack,
        "period": {"from": report.period_start.isoformat(), "to": report.period_end.isoformat()},
        "data_stale": report.data_stale,
        "snapshot": report.snapshot,
        "decisions": _decisions(db, report.tenant_id),
    }
    system = INSIGHT_SYSTEM + "\n\n## Playbook của gói\n" + playbook(report.pack)
    messages = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]
    sess = ToolSession()
    try:
        out = run_model(call, runner or default_runner(ctx, db), system, messages, sess, INSIGHT_TOOL, 120)
    except Exception:
        log.exception("weekly-insight lỗi", extra={"report_id": report.id})
        out = None
    _finish_cost(db, report.tenant_id, sess)
    if not out:
        report.actions_draft = []  # đánh dấu đã thử, không thử lại mỗi vòng worker
        return False
    actions = [str(a).strip().replace("\n", " ")[:300] for a in out.get("actions") or [] if str(a).strip()]
    report.insight_draft_md = str(out.get("insight_md") or "").strip()[:MAX_INSIGHT] or None
    report.actions_draft = actions[:MAX_ACTIONS]
    return report.insight_draft_md is not None


def _clean_failures(items: list[Any] | None) -> list[dict[str, Any]]:
    """Chỉ giữ tên test và số dòng lỗi; bỏ dòng dữ liệu (có thể chứa giá trị gốc)."""
    out: list[dict[str, Any]] = []
    for f in items or []:
        if isinstance(f, dict):
            rows = f.get("rows")
            out.append(
                {"test": f.get("test"), "failures": f.get("failures", len(rows) if isinstance(rows, list) else None)}
            )
    return out[:30]


def incident_triage(db: Session, run: PipelineRun, *, caller: ModelCaller | None = None) -> bool:
    call = _agent_caller(caller)
    if call is None:
        return False
    syncs = db.scalars(select(SourceSync).where(SourceSync.tenant_id == run.tenant_id))
    payload = {
        "job": run.job,
        "status": run.status,
        "failed_step": run.failed_step,
        "steps": run.steps,
        "blocking_failures": _clean_failures(run.blocking_failures),
        "sources": [
            {
                "source": s.source,
                "last_status": s.last_status,
                "last_error_code": s.last_error_code,
                "last_success_at": s.last_success_at,
            }
            for s in syncs
        ],
    }
    messages = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]
    sess = ToolSession()
    ctx = internal_ctx(db, run.tenant_id)
    try:
        out = run_model(call, default_runner(ctx, db), TRIAGE_SYSTEM, messages, sess, TRIAGE_TOOL, 120)
    except Exception:
        log.exception("incident-triage lỗi", extra={"run_id": run.run_id})
        out = None
    _finish_cost(db, run.tenant_id, sess)
    run.triage_md = str((out or {}).get("triage_md") or "").strip()[:4000]
    return bool(run.triage_md)


def run_agents(db: Session, *, caller: ModelCaller | None = None, limit: int = 5) -> dict[str, int]:
    """Một vòng worker: bản nháp cho báo cáo mới dựng, phân tích cho lần chạy lỗi mới. Không có khóa API thì bỏ qua."""
    if _agent_caller(caller) is None:
        return {}
    since = now_utc() - timedelta(days=7)
    reports = db.scalars(
        select(Report)
        .where(
            Report.status == "draft",
            Report.insight_draft_md.is_(None),
            Report.actions_draft.is_(None),
            Report.built_at > since,
        )
        .order_by(Report.built_at)
        .limit(limit)
    ).all()
    n_ins = sum(1 for r in reports if weekly_insight(db, r, caller=caller))
    runs = db.scalars(
        select(PipelineRun)
        .where(
            PipelineRun.status.in_(("failed", "blocked")),
            PipelineRun.triage_md.is_(None),
            PipelineRun.started_at > now_utc() - timedelta(days=2),
        )
        .order_by(PipelineRun.started_at)
        .limit(limit)
    ).all()
    n_tri = sum(1 for r in runs if incident_triage(db, r, caller=caller))
    return {"insight_drafts": n_ins, "triage": n_tri}
