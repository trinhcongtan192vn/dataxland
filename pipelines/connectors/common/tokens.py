"""Token gian hàng trong Secret Manager (spec 01 §2.1, §2.2, FR-ING-08).

Secret theo khách (`secret_ref`) là JSON `{shop_id, access_token, refresh_token, expires_at, ...}`. Khóa ứng dụng
đối tác nằm ở secret `dx-<source>-app`. Làm mới trước mỗi lần chạy (khi còn dưới `REFRESH_MARGIN`) và khi nguồn báo
hết hạn; token mới ghi thành phiên bản mới của cùng secret.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from connectors.base import SourceError
from dx_common.secrets import SecretNotFound, get_secret_store
from dx_common.tenants.naming import app_secret
from dx_common.timeutil import iso_z, now_utc

REFRESH_MARGIN = timedelta(minutes=30)

RefreshFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class AuthRevoked(Exception):
    """Nền tảng từ chối refresh token: gian hàng đã thu hồi quyền."""


def load_app(source: str) -> dict[str, Any]:
    try:
        return dict(json.loads(get_secret_store().get(app_secret(source))))
    except SecretNotFound as exc:
        raise SourceError("auth_revoked", f"chưa có secret {app_secret(source)}") from exc


class TokenManager:
    def __init__(
        self, secret_name: str, app: dict[str, Any], refresh_fn: RefreshFn, clock: Callable[[], datetime] = now_utc
    ) -> None:
        self.secret_name = secret_name
        self.app = app
        self.refresh_fn = refresh_fn
        self.clock = clock
        try:
            self.data: dict[str, Any] = dict(json.loads(get_secret_store().get(secret_name)))
        except SecretNotFound as exc:
            raise SourceError("auth_revoked", f"chưa có secret {secret_name}") from exc

    @property
    def access_token(self) -> str:
        return str(self.data.get("access_token") or "")

    def expires_at(self) -> datetime | None:
        raw = self.data.get("expires_at")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))

    def ensure_fresh(self) -> None:
        exp = self.expires_at()
        if exp is None or exp - self.clock() < REFRESH_MARGIN:
            self.refresh()

    def refresh(self) -> None:
        try:
            new = self.refresh_fn(self.app, self.data)
        except AuthRevoked as exc:
            raise SourceError("auth_revoked", "nền tảng từ chối làm mới token") from exc
        merged = {**self.data, **new}
        if "expires_in" in new:
            merged["expires_at"] = iso_z(self.clock() + timedelta(seconds=int(new["expires_in"])))
            merged.pop("expires_in", None)
        get_secret_store().put(self.secret_name, json.dumps(merged, sort_keys=True))
        self.data = merged
