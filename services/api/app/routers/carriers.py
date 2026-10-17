"""Hãng vận chuyển (FR-ING-09, ADR 0005).

| Endpoint | Việc |
|---|---|
| `GET /v1/carriers` | Hãng khách đã bật, URL webhook (người có quyền nhập liệu), số vận đơn, lần nhận gần nhất |
| `POST /v1/webhooks/carriers/{hãng}/{khách}/{token}` | GHN, GHTK đẩy trạng thái vận đơn; token HMAC theo khách và hãng |
| `POST /v1/inputs/carrier-files` | Tải file đối soát J&T (xlsx, csv); pipeline đọc ở lần chạy kế tiếp |
| `GET /v1/inputs/carrier-files` | File đã tải và kết quả nạp |

Webhook chỉ lưu trường vận đơn (mã, mã đơn của shop, trạng thái, thời điểm, phí, COD); tên, số điện thoại, địa chỉ
người nhận trong payload bị bỏ ngay (NFR-03). Phí và COD đầy đủ do connector lấy qua API chi tiết vận đơn.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, get_ctx, load_tenant
from app.auth.permissions import allowed, require
from app.db import get_db
from app.db.models import CarrierEvent, CarrierFile
from app.errors import ApiError
from dx_common.config import get_settings
from dx_common.events import publish
from dx_common.ids import new_ulid
from dx_common.timeutil import VN_TZ, now_utc

router = APIRouter(tags=["carriers"])

WEBHOOK_CARRIERS = ("ghn", "ghtk")
FILE_CARRIERS = ("jnt",)
MAX_FILE_BYTES = 20 * 1024 * 1024
LABEL = {"ghn": "Giao Hàng Nhanh", "ghtk": "Giao Hàng Tiết Kiệm", "jnt": "J&T Express"}


def hook_token(tenant_id: str, carrier: str) -> str:
    key = (get_settings().internal_api_token or "").encode()
    return hmac.new(key, f"carrier:{tenant_id}:{carrier}".encode(), hashlib.sha256).hexdigest()[:32]


def webhook_url(tenant_id: str, carrier: str) -> str:
    base = get_settings().dx_api_public_url.rstrip("/")
    return f"{base}/v1/webhooks/carriers/{carrier}/{tenant_id}/{hook_token(tenant_id, carrier)}"


# --------------------------------------------------------------------------- đọc payload


def _get(d: dict[str, Any], *keys: str) -> Any:
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def _num(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _time(v: Any) -> datetime:
    if v in (None, ""):
        return now_utc()
    if isinstance(v, int | float) or str(v).isdigit():
        return datetime.fromtimestamp(int(v), tz=UTC)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(s)
    except ValueError:
        return now_utc()
    # Chuỗi không kèm múi giờ của hãng là giờ Việt Nam.
    return ts.astimezone(UTC) if ts.tzinfo else ts.replace(tzinfo=VN_TZ).astimezone(UTC)


def parse_event(carrier: str, p: dict[str, Any]) -> dict[str, Any]:
    """Chỉ giữ trường vận đơn. GHN: OrderCode, ClientOrderCode, Status, Time, TotalFee, CODAmount.
    GHTK: label_id, partner_id, status_id, action_time, fee, pick_money."""
    if carrier == "ghn":
        out = {
            "waybill": _get(p, "OrderCode", "order_code"),
            "client_order_code": _get(p, "ClientOrderCode", "client_order_code"),
            "status_raw": _get(p, "Status", "status"),
            "event_at": _time(_get(p, "Time", "updated_date")),
            "shipping_fee": _num(_get(p, "TotalFee", "total_fee")),
            "cod_amount": _num(_get(p, "CODAmount", "cod_amount")),
        }
    else:
        out = {
            "waybill": _get(p, "label_id", "label"),
            "client_order_code": _get(p, "partner_id"),
            "status_raw": _get(p, "status_id", "status"),
            "event_at": _time(_get(p, "action_time", "modified")),
            "shipping_fee": _num(_get(p, "fee", "ship_money")),
            "cod_amount": _num(_get(p, "pick_money")),
        }
    if not out["waybill"] or out["status_raw"] is None:
        raise ApiError(422, "WEBHOOK_PAYLOAD_INVALID", "Thiếu mã vận đơn hoặc trạng thái")
    out["waybill"], out["status_raw"] = str(out["waybill"]), str(out["status_raw"])
    if out["client_order_code"] is not None:
        out["client_order_code"] = str(out["client_order_code"])
    return out


@router.post("/v1/webhooks/carriers/{carrier}/{tenant_id}/{token}")
async def carrier_webhook(
    carrier: str, tenant_id: str, token: str, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    if carrier not in WEBHOOK_CARRIERS or not hmac.compare_digest(token, hook_token(tenant_id, carrier)):
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    _, cfg = load_tenant(db, tenant_id)
    if carrier not in cfg.carriers():
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy")
    try:
        payload = await request.json()
    except ValueError:
        payload = dict(await request.form())
    items = payload if isinstance(payload, list) else [payload]
    n = 0
    for p in items:
        if not isinstance(p, dict):
            continue
        ev = parse_event(carrier, p)
        new_id = db.execute(
            insert(CarrierEvent)
            .values(id=new_ulid(), tenant_id=tenant_id, carrier=carrier, **ev)
            .on_conflict_do_nothing(constraint="uq_carrier_events")
            .returning(CarrierEvent.id)
        ).scalar_one_or_none()
        n += 1 if new_id else 0
    return {"success": True, "received": n}


# --------------------------------------------------------------------------- cổng


class CarrierOut(BaseModel):
    carrier: str
    label: str
    kind: str
    webhook_url: str | None
    waybills: int
    last_event_at: datetime | None
    guide: str


@router.get("/v1/carriers", response_model=list[CarrierOut])
def list_carriers(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[CarrierOut]:
    require(ctx, "inputs.read", resource="carriers")
    can_write = allowed(ctx.role, "inputs.write", resource="carriers")
    out: list[CarrierOut] = []
    for c in ctx.tenant.carriers():
        stats = db.execute(
            select(func.count(func.distinct(CarrierEvent.waybill)), func.max(CarrierEvent.created_at)).where(
                CarrierEvent.tenant_id == ctx.tenant_id, CarrierEvent.carrier == c
            )
        ).one()
        out.append(
            CarrierOut(
                carrier=c,
                label=LABEL[c],
                kind="webhook" if c in WEBHOOK_CARRIERS else "file",
                webhook_url=webhook_url(ctx.tenant_id, c) if c in WEBHOOK_CARRIERS and can_write else None,
                waybills=int(stats[0] or 0),
                last_event_at=stats[1],
                guide=c,
            )
        )
    return out


class CarrierFileOut(BaseModel):
    id: str
    carrier: str
    filename: str
    size_bytes: int
    status: str
    rows_loaded: int | None
    error_message_vi: str | None
    created_at: datetime


def _out(f: CarrierFile) -> CarrierFileOut:
    return CarrierFileOut(
        id=f.id,
        carrier=f.carrier,
        filename=f.filename,
        size_bytes=f.size_bytes,
        status=f.status,
        rows_loaded=f.rows_loaded,
        error_message_vi=f.error_message_vi,
        created_at=f.created_at,
    )


def save_carrier_file(tenant_id: str, name: str, content: bytes) -> str:
    """`<METADATA_BUCKET>/carrier-files/<khách>/<tên>` (GCS hoặc thư mục local)."""
    root = get_settings().metadata_bucket.rstrip("/")
    if root.startswith("gs://"):  # pragma: no cover - cần GCS
        import google.cloud.storage as storage

        bucket, _, prefix = root[5:].partition("/")
        blob = "/".join(x for x in (prefix, "carrier-files", tenant_id, name) if x)
        storage.Client().bucket(bucket).blob(blob).upload_from_string(content)
        return f"gs://{bucket}/{blob}"
    path = Path(root) / "carrier-files" / tenant_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path.resolve())


@router.post("/v1/inputs/carrier-files", response_model=CarrierFileOut, status_code=201)
async def upload_carrier_file(
    file: UploadFile = File(...), ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)
) -> CarrierFileOut:
    require(ctx, "inputs.write", resource="carriers")
    if "jnt" not in ctx.tenant.carriers():
        raise ApiError(400, "CARRIER_NOT_IN_TENANT", "Khách chưa bật nguồn J&T Express")
    name = file.filename or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ("xlsx", "csv"):
        raise ApiError(400, "FILE_TYPE", "Chỉ nhận file .xlsx hoặc .csv")
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "File lớn hơn 20 MB")
    fid = new_ulid()
    path = save_carrier_file(ctx.tenant_id, f"{fid}.{ext}", content)
    row = CarrierFile(
        id=fid,
        tenant_id=ctx.tenant_id,
        carrier="jnt",
        filename=name[:255],
        size_bytes=len(content),
        storage_path=path,
        uploaded_by=ctx.user_id,
    )
    db.add(row)
    db.flush()
    audit(db, action="inputs.carrier_file_uploaded", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=fid)
    publish("inputs.changed", ctx.tenant_id, {"kind": "carrier_files"}, "s6-portal", bind=db)
    db.refresh(row)
    return _out(row)


@router.get("/v1/inputs/carrier-files", response_model=list[CarrierFileOut])
def list_carrier_files(ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> list[CarrierFileOut]:
    require(ctx, "inputs.read", resource="carriers")
    rows = db.scalars(
        select(CarrierFile).where(CarrierFile.tenant_id == ctx.tenant_id).order_by(CarrierFile.created_at.desc())
    )
    return [_out(f) for f in rows]
