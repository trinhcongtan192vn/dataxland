"""Hạ tầng test của services/api.

- Postgres tạm (`dx_common.testing.ephemeral_postgres`), chạy `alembic upgrade head` một lần cho cả phiên.
- Trước mỗi test: xóa dữ liệu mọi bảng, đồng bộ `tenants/` của repo, tạo người dùng giả lập.
- Firebase giả: token `uid:<firebase_uid>`; `bad`, `expired`, `revoked` bị từ chối.
- Kênh email và Telegram giả ghi lại tin đã gửi.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
API_DIR = REPO / "services" / "api"

os.environ.setdefault("DX_ENV", "local")
os.environ["INTERNAL_API_TOKEN"] = "test-internal-token"
os.environ["CUBE_API_SECRET"] = "test-cube-secret"
os.environ["MCP_SESSION_SECRET"] = "test-mcp-secret"
os.environ["MCP_URL"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["DX_PUBLIC_BASE_URL"] = "https://app.test"
os.environ["DX_TEAM_EMAIL"] = "team@dataxland.test"
os.environ["TELEGRAM_TEAM_CHAT_ID"] = "-1001"
os.environ["SMTP_HOST"] = ""
os.environ["DX_REPO_ROOT"] = str(REPO)

from dx_common.testing import ephemeral_postgres  # noqa: E402

INTERNAL = {"Authorization": "Bearer test-internal-token", "X-Service": "dagster"}


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with ephemeral_postgres() as url:
        env = dict(os.environ, DATABASE_URL=url)
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR, env=env, check=True, capture_output=True
        )
        os.environ["DATABASE_URL"] = url
        from dx_common.config import reset_settings_cache
        from dx_common.db import reset_engines

        reset_settings_cache()
        reset_engines()
        yield url


@dataclass
class FakeUser:
    uid: str
    email: str
    name: str


USERS = {
    "owner_seller": FakeUser("fb-owner-seller", "owner@demo-seller.example", "Chủ Shop Demo"),
    "member_seller": FakeUser("fb-member-seller", "member@demo-seller.example", "Nhân viên Shop"),
    "owner_agency": FakeUser("fb-owner-agency", "owner@demo-agency.example", "Chủ Brand Demo"),
    "partner": FakeUser("fb-partner", "am@agency-demo.example", "AM Agency"),
    "data_lead": FakeUser("fb-lead", "lead@dataxland.test", "Data Lead"),
    "engineer": FakeUser("fb-eng", "eng@dataxland.test", "Engineer"),
    "outsider": FakeUser("fb-out", "out@example.com", "Người ngoài"),
}


class FakeVerifier:
    def verify(self, token: str) -> Any:
        from app.auth.firebase import InvalidToken, VerifiedToken

        if not token.startswith("uid:"):
            raise InvalidToken(token)
        uid = token[4:]
        u = next((x for x in USERS.values() if x.uid == uid), None)
        email = u.email if u else f"{uid}@example.com"
        return VerifiedToken(
            uid=uid, email=email, email_verified=True, name=u.name if u else uid, sign_in_provider="password"
        )


class FakeChannel:
    def __init__(self, name: str, fail: bool = False, connection_error: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.connection_error = connection_error
        self.sent: list[tuple[Any, Any]] = []

    def supports(self, recipient: Any) -> bool:
        if self.name == "email":
            return recipient.kind in ("email", "team") and "@" in recipient.address
        if self.name == "telegram":
            return recipient.kind in ("telegram_chat", "team") and recipient.address.lstrip("-").isdigit()
        return True

    async def send(self, recipient: Any, message: Any) -> Any:
        from app.notify.types import DeliveryResult

        if self.fail:
            return DeliveryResult(ok=False, error_code="FAKE_DOWN", connection_error=self.connection_error)
        self.sent.append((recipient, message))
        return DeliveryResult(ok=True)


@pytest.fixture()
def channels() -> Iterator[dict[str, FakeChannel]]:
    from app.notify.channels import register_channel, reset_channels

    reset_channels()
    fakes = {"email": FakeChannel("email"), "telegram": FakeChannel("telegram")}
    for c in fakes.values():
        register_channel(c)
    yield fakes
    reset_channels()


TABLES_KEEP = {"alembic_version"}


def _truncate(url: str) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(url)
    with eng.begin() as conn:
        names = [r[0] for r in conn.execute(text("select tablename from pg_tables where schemaname = 'public'"))]
        names = [n for n in names if n not in TABLES_KEEP]
        if names:
            conn.execute(text("truncate " + ", ".join(f'"{n}"' for n in names) + " restart identity cascade"))
    eng.dispose()


def seed_people(db: Any) -> dict[str, str]:
    """Tạo người dùng, membership, partner grant cho hai khách giả lập. Trả {khóa: user_id}."""
    from app.db.models import Membership, PartnerGrant, PartnerUser, User
    from dx_common.timeutil import now_utc

    ids: dict[str, str] = {}
    for key, u in USERS.items():
        staff = {"data_lead": "data_lead", "engineer": "engineer"}.get(key)
        row = User(firebase_uid=u.uid, email=u.email, display_name=u.name, staff_role=staff)
        db.add(row)
        db.flush()
        ids[key] = row.id
    db.add(Membership(user_id=ids["owner_seller"], tenant_id="demo_seller", role="owner"))
    db.add(
        Membership(
            user_id=ids["member_seller"],
            tenant_id="demo_seller",
            role="member",
            metric_allowlist=["net_revenue", "order_count"],
        )
    )
    db.add(Membership(user_id=ids["owner_agency"], tenant_id="demo_agency", role="owner"))
    db.add(PartnerUser(user_id=ids["partner"], partner_id="demo_partner"))
    db.add(
        PartnerGrant(
            tenant_id="demo_agency", partner_id="demo_partner", granted_by=ids["owner_agency"], granted_at=now_utc()
        )
    )
    db.flush()
    return ids


@pytest.fixture()
def db_url(pg_url: str) -> Iterator[str]:
    _truncate(pg_url)
    from app.registry_sync import sync_tenants
    from dx_common.db import session_scope

    with session_scope(pg_url) as db:
        sync_tenants(db, REPO / "tenants")
        for t in ("demo_seller", "demo_agency"):
            from app.db.models import Tenant

            row = db.get(Tenant, t)
            assert row is not None
            row.bootstrap_required = False
    yield pg_url


@pytest.fixture()
def people(db_url: str) -> dict[str, str]:
    from dx_common.db import session_scope

    with session_scope(db_url) as db:
        return seed_people(db)


@pytest.fixture()
def client(db_url: str, people: dict[str, str], channels: dict[str, FakeChannel]) -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from app.auth.firebase import set_token_verifier
    from app.main import create_app

    set_token_verifier(FakeVerifier())
    with TestClient(create_app()) as c:
        yield c
    set_token_verifier(None)


def auth(key: str, tenant: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer uid:{USERS[key].uid}"}
    if tenant:
        h["X-Tenant-Id"] = tenant
    return h


@pytest.fixture()
def session(db_url: str) -> Iterator[Any]:
    from dx_common.db import session_factory

    s = session_factory(db_url)()
    try:
        yield s
        s.commit()
    finally:
        s.close()
