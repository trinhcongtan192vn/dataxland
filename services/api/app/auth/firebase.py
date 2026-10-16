"""Xác minh Firebase ID token (FR-AUTH-01, spec 05 §3.1).

`verify_id_token(check_revoked=True)`. Ở `local`, `FIREBASE_AUTH_EMULATOR_HOST` làm firebase-admin dùng emulator.
Test thay `TokenVerifier` qua `set_token_verifier`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from dx_common.config import get_settings
from dx_common.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class VerifiedToken:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None
    sign_in_provider: str | None


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedToken: ...


class FirebaseVerifier:
    def __init__(self) -> None:
        import firebase_admin
        from firebase_admin import credentials

        s = get_settings()
        if s.firebase_auth_emulator_host:
            os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", s.firebase_auth_emulator_host)
        if not firebase_admin._apps:
            opts = {"projectId": s.firebase_project_id}
            if s.firebase_auth_emulator_host:
                firebase_admin.initialize_app(credentials.AnonymousCredentials(), options=opts)
            else:
                firebase_admin.initialize_app(options=opts)

    def verify(self, token: str) -> VerifiedToken:
        from firebase_admin import auth

        try:
            claims: dict[str, Any] = auth.verify_id_token(token, check_revoked=True)
        except Exception as exc:  # hết hạn, sai chữ ký, bị thu hồi...
            raise InvalidToken(type(exc).__name__) from exc
        fb = claims.get("firebase") or {}
        return VerifiedToken(
            uid=str(claims["uid"]),
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified")),
            name=claims.get("name"),
            sign_in_provider=fb.get("sign_in_provider") if isinstance(fb, dict) else None,
        )


_verifier: TokenVerifier | None = None


def get_token_verifier() -> TokenVerifier:
    global _verifier
    if _verifier is None:
        _verifier = FirebaseVerifier()
    return _verifier


def set_token_verifier(v: TokenVerifier | None) -> None:
    global _verifier
    _verifier = v


def set_custom_claims(firebase_uid: str, claims: dict[str, Any]) -> None:
    """Đặt claims `{role_hint, tenant_ids, partner_id}` chỉ để giao diện hiện menu (spec 05 §3.2).

    Backend không dùng claims để quyết định quyền. Lỗi ở đây không làm hỏng request.
    """
    if isinstance(_verifier, FirebaseVerifier) or (_verifier is None and get_settings().firebase_project_id):
        try:
            from firebase_admin import auth

            get_token_verifier()
            auth.set_custom_user_claims(firebase_uid, claims)
        except Exception as exc:
            log.warning("không đặt được custom claims: %s", type(exc).__name__)
