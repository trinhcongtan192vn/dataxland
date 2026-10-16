"""Kết nối gian hàng trên sàn qua OAuth (spec 05 §6.7, spec 01 §2.3).

- `POST /v1/connect/{source}/start`: chỉ `data_lead`; tạo `oauth_states` (lưu hash của `state`, hết hạn 15 phút),
  trả `{authorize_url}`.
- `GET /v1/connect/{source}/callback`: sàn chuyển trình duyệt về đây. Kiểm `state` (dùng một lần), đổi mã lấy token,
  ghi secret `dx-<tenant_id>-<source>-<account_id>`, cập nhật `source_syncs`, chuyển hướng về
  `/ops/tenants/<id>?connected=<source>`. Không token nào được trả về trình duyệt hay ghi log.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.auth.context import AuthContext, get_ctx
from app.auth.permissions import require
from app.db import get_db
from app.db.models import OAuthState, SourceSync
from app.errors import ApiError
from dx_common import marketplace as mp
from dx_common.config import get_settings
from dx_common.ids import random_token
from dx_common.logging import get_logger
from dx_common.secrets import SecretNotFound, get_secret_store
from dx_common.tenants.naming import app_secret, source_secret
from dx_common.timeutil import now_utc

router = APIRouter(tags=["connect"])
log = get_logger(__name__)
STATE_TTL = timedelta(minutes=15)


def _default_http() -> httpx.Client:
    return httpx.Client(timeout=30)


_http_factory: Callable[[], httpx.Client] = _default_http


def set_http_factory(f: Callable[[], httpx.Client] | None) -> None:
    """Cho test thay client HTTP gọi sàn."""
    global _http_factory
    _http_factory = f or _default_http


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _check_source(source: str) -> None:
    if source not in mp.SOURCES:
        raise ApiError(404, "SOURCE_UNKNOWN", f"Không hỗ trợ kết nối {source}")


def load_app(source: str) -> dict[str, Any]:
    try:
        return dict(json.loads(get_secret_store().get(app_secret(source))))
    except SecretNotFound as exc:
        raise ApiError(
            409,
            "APP_NOT_CONFIGURED",
            f"Chưa cấu hình ứng dụng đối tác {source} (secret {app_secret(source)}). "
            f"Xem hướng dẫn ở /ops/integrations/{source}",
        ) from exc


def callback_url(source: str) -> str:
    return f"{get_settings().marketplace_oauth_redirect_base.rstrip('/')}/v1/connect/{source}/callback"


@router.post("/v1/connect/{source}/start")
def start(source: str, ctx: AuthContext = Depends(get_ctx), db: Session = Depends(get_db)) -> dict[str, str]:
    require(ctx, "connect.sources")
    _check_source(source)
    app = load_app(source)
    state = random_token(24)
    db.add(
        OAuthState(
            state_hash=_hash(state),
            source=source,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id or "",
            expires_at=now_utc() + STATE_TTL,
        )
    )
    if source == "shopee":
        # Shopee trả `code`, `shop_id` về đúng URL redirect; `state` đi kèm trong URL đó.
        url = mp.shopee_authorize_url(app, f"{callback_url(source)}?{urlencode({'state': state})}")
    elif source == "tiktok_shop":
        url = mp.tiktok_authorize_url(app, state)  # URL callback đặt trong cấu hình ứng dụng trên Partner Center
    else:
        url = mp.lazada_authorize_url(app, callback_url(source), state)
    audit(db, action="source.connect_started", tenant_id=ctx.tenant_id, actor_user_id=ctx.user_id, target=source)
    return {"authorize_url": url}


def _ui(tenant_id: str | None, **params: str) -> RedirectResponse:
    base = get_settings().dx_public_base_url.rstrip("/")
    path = f"/ops/tenants/{tenant_id}" if tenant_id else "/ops/integrations"
    return RedirectResponse(f"{base}{path}?{urlencode(params)}", status_code=302)


@router.get("/v1/connect/{source}/callback")
def callback(
    source: str,
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    shop_id: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    _check_source(source)
    row = db.get(OAuthState, _hash(state)) if state else None
    if row is None or row.source != source or row.used_at is not None or row.expires_at < now_utc():
        return _ui(row.tenant_id if row else None, connect_error="STATE_INVALID", source=source)
    row.used_at = now_utc()
    db.flush()
    if error or not code:
        audit(
            db,
            action="source.connect_failed",
            tenant_id=row.tenant_id,
            actor_user_id=row.user_id,
            target=source,
            detail={"reason": "denied"},
        )
        return _ui(row.tenant_id, connect_error="DENIED", source=source)
    if source == "shopee" and not shop_id:
        return _ui(row.tenant_id, connect_error="SHOP_ID_MISSING", source=source)
    app = load_app(source)
    try:
        with _http_factory() as client:
            if source == "shopee":
                res = mp.shopee_exchange(app, code, str(shop_id), client)
            elif source == "tiktok_shop":
                res = mp.tiktok_exchange(app, code, client)
            else:
                res = mp.lazada_exchange(app, code, client)
    except (mp.OAuthError, httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("đổi mã OAuth thất bại", extra={"source": source, "error": type(exc).__name__})
        audit(
            db,
            action="source.connect_failed",
            tenant_id=row.tenant_id,
            actor_user_id=row.user_id,
            target=source,
            detail={"reason": "exchange_failed"},
        )
        return _ui(row.tenant_id, connect_error="EXCHANGE_FAILED", source=source)
    name = source_secret(row.tenant_id, source, res.account_id)
    get_secret_store().put(name, json.dumps(res.secret, sort_keys=True))
    sync = db.scalar(
        select(SourceSync).where(
            SourceSync.tenant_id == row.tenant_id, SourceSync.source == source, SourceSync.account_id == res.account_id
        )
    )
    if sync is None:
        sync = SourceSync(tenant_id=row.tenant_id, source=source, account_id=res.account_id)
        db.add(sync)
    sync.connected_at = now_utc()
    sync.last_error_code = None
    audit(
        db,
        action="source.connected",
        tenant_id=row.tenant_id,
        actor_user_id=row.user_id,
        target=source,
        detail={"account_id": res.account_id, "secret_ref": name},
    )
    return _ui(row.tenant_id, connected=source, account_id=res.account_id, secret_ref=name)
