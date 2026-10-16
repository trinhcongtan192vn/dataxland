"""FR-AUTH-01..04, NFR-02, spec 05 §3, §4, §9."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import inspect, select

from app.auth.permissions import ACTIONS, ROLES, allowed, cell
from tests.conftest import INTERNAL, auth

# Ma trận chép nguyên từ spec 05 §4. "✓" = True, ô trống = False, ghi chú = giá trị chuỗi.
SPEC_MATRIX: dict[str, dict[str, Any]] = {
    "metrics.read": {
        "owner": True,
        "member": "scoped",
        "partner": "scoped",
        "data_lead": True,
        "engineer": True,
        "group": "scoped",
    },
    "reports.read": {
        "owner": True,
        "member": True,
        "partner": "agency",
        "data_lead": True,
        "engineer": True,
        "group": "summary",
    },
    "reports.edit": {"data_lead": True},
    "reports.approve": {"data_lead": True},
    "inputs.read": {"owner": True, "member": True, "partner": "budgets", "data_lead": True, "engineer": True},
    "inputs.write": {"owner": True, "partner": "budgets", "data_lead": True},
    "decisions.read": {"owner": True, "member": True, "partner": True, "data_lead": True, "engineer": True},
    "decisions.write": {"owner": True, "partner": True, "data_lead": True},
    "users.manage": {"owner": True, "data_lead": True},
    "partners.manage": {"owner": True},
    "telegram.link_self": {"owner": True, "member": True, "partner": True, "data_lead": True, "engineer": True},
    "telegram.link_group": {"owner": True},
    "telegram.manage": {"owner": True},
    "connect.sources": {"data_lead": True},
    "ops.read": {"data_lead": True, "engineer": True},
    "ops.write": {"data_lead": True},
    "healthchecks.review": {"data_lead": True},
}


def test_alembic_upgrade_head_creates_all_tables(pg_url: str) -> None:
    from sqlalchemy import create_engine

    names = set(inspect(create_engine(pg_url)).get_table_names())
    expected = {
        "tenants",
        "users",
        "memberships",
        "invitations",
        "partners",
        "partner_users",
        "partner_grants",
        "audit_log",
        "product_costs",
        "ad_budgets",
        "upload_jobs",
        "events",
        "event_offsets",
        "event_processed",
        "event_dead_letters",
        "notifications",
        "pipeline_runs",
        "source_syncs",
        "erasure_log",
        "metric_queries",
        "reports",
        "report_recipients",
        "report_opens",
        "decisions",
        "telegram_link_codes",
        "telegram_links",
        "telegram_rate",
        "health_checks",
        "health_check_files",
        "oauth_states",
        "fx_manual_rates",
        "metric_requests",
        "ask_logs",
        "rate_counters",
    }
    assert expected <= names, expected - names


def test_fr_auth_02_permission_matrix_cells() -> None:
    assert set(ACTIONS) == set(SPEC_MATRIX)
    for action, row in SPEC_MATRIX.items():
        for role in ROLES:
            assert cell(role, action) == row.get(role, False), (action, role)
    # Ô có điều kiện.
    assert allowed("partner", "inputs.write", resource="ad_budgets")
    assert not allowed("partner", "inputs.write", resource="product_costs")
    assert allowed("partner", "reports.read", pack="agency")
    assert not allowed("partner", "reports.read", pack="seller")


def test_fr_auth_01_firebase_token(client: Any) -> None:
    r = client.get("/v1/me", headers=auth("owner_seller"))
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "owner@demo-seller.example"
    assert [t["tenant_id"] for t in body["tenants"]] == ["demo_seller"]
    for bad in ("bad", "expired", "revoked"):
        r = client.get("/v1/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["code"] == "INVALID_TOKEN"
    assert client.get("/v1/me").status_code == 401


def test_first_login_creates_user_and_accepts_invitation(client: Any, session: Any) -> None:
    from datetime import timedelta

    from app.db.models import Invitation, Membership, User
    from dx_common.timeutil import now_utc

    session.add(
        Invitation(
            tenant_id="demo_seller",
            email="new@demo-seller.example",
            role="member",
            metric_allowlist=["net_revenue"],
            token_hash="h1",
            expires_at=now_utc() + timedelta(days=1),
        )
    )
    session.commit()
    r = client.get("/v1/me", headers={"Authorization": "Bearer uid:fb-new"})
    assert r.status_code == 200
    session.expire_all()
    u = session.scalar(select(User).where(User.firebase_uid == "fb-new"))
    assert u is not None
    # Email giả của FakeVerifier là fb-new@example.com nên lời mời khác email không được nhận.
    assert session.scalar(select(Membership).where(Membership.user_id == u.id)) is None


def test_tenant_required_and_forbidden(client: Any) -> None:
    # Nhân viên thấy nhiều khách: không gửi X-Tenant-Id → 400 TENANT_REQUIRED.
    r = client.get("/v1/inputs/ad-budgets", headers=auth("data_lead"))
    assert r.status_code == 400 and r.json()["code"] == "TENANT_REQUIRED"
    # Người dùng một khách: tự chọn khách đó.
    assert client.get("/v1/inputs/product-costs", headers=auth("owner_seller")).status_code == 200
    r = client.get("/v1/inputs/product-costs", headers=auth("outsider", "demo_seller"))
    assert r.status_code == 403 and r.json()["code"] == "TENANT_FORBIDDEN"


def test_request_id_header(client: Any) -> None:
    r = client.get("/v1/me", headers={**auth("owner_seller"), "X-Request-Id": "abcdefgh1234"})
    assert r.headers["X-Request-Id"] == "abcdefgh1234"
    r = client.get("/v1/me", headers=auth("owner_seller"))
    assert len(r.headers["X-Request-Id"]) == 26


def test_internal_endpoints_reject_user_token(client: Any) -> None:
    r = client.get("/v1/internal/tenants", headers={**auth("data_lead"), "X-Service": "dagster"})
    assert r.status_code == 403
    r = client.get("/v1/internal/tenants", headers=INTERNAL)
    assert r.status_code == 200
    assert {t["tenant_id"] for t in r.json()} >= {"demo_seller", "demo_agency"}
    # Token nội bộ không dùng được cho endpoint người dùng.
    r = client.get("/v1/me", headers=INTERNAL)
    assert r.status_code == 403


def test_fr_auth_04_revoke_is_immediate(client: Any, session: Any) -> None:
    from app.db.models import PartnerGrant, TelegramLink

    assert client.get("/v1/tenants/demo_agency", headers=auth("partner")).status_code == 200
    me = client.get("/v1/me", headers=auth("partner")).json()
    assert [t["tenant_id"] for t in me["tenants"]] == ["demo_agency"]
    assert me["tenants"][0]["role"] == "partner"
    session.add(TelegramLink(chat_id=555, chat_type="private", user_id=me["user_id"], tenant_id="demo_agency"))
    session.commit()

    grants = client.get("/v1/partners/grants", headers=auth("owner_agency")).json()
    assert len(grants) == 1
    assert client.delete(f"/v1/partners/grants/{grants[0]['id']}", headers=auth("owner_agency")).status_code == 204

    r = client.get("/v1/tenants/demo_agency", headers=auth("partner"))
    assert r.status_code == 403 and r.json()["code"] == "TENANT_FORBIDDEN"
    session.expire_all()
    link = session.scalar(select(TelegramLink).where(TelegramLink.chat_id == 555))
    assert link.status == "revoked" and link.revoked_reason == "access_lost"
    g = session.get(PartnerGrant, grants[0]["id"])
    assert g.revoked_at is not None
    # Owner seller không quản lý được grant của khách khác.
    r = client.get("/v1/partners/grants", headers=auth("owner_seller", "demo_agency"))
    assert r.status_code == 403


def test_partner_grant_flow(client: Any) -> None:
    r = client.get("/v1/partners", headers=auth("owner_seller"))
    assert r.status_code == 200 and r.json()[0]["partner_id"] == "demo_partner"
    r = client.post("/v1/partners/grants", json={"partner_id": "demo_partner"}, headers=auth("owner_seller"))
    assert r.status_code == 201
    me = client.get("/v1/me", headers=auth("partner")).json()
    assert {t["tenant_id"] for t in me["tenants"]} == {"demo_agency", "demo_seller"}
    r = client.post("/v1/partners/grants", json={"partner_id": "demo_partner"}, headers=auth("owner_seller"))
    assert r.status_code == 409
    # Member không quản lý được agency.
    assert client.get("/v1/partners/grants", headers=auth("member_seller")).status_code == 403


def test_members_last_owner_and_removal(client: Any, session: Any) -> None:
    from app.db.models import TelegramLink

    members = client.get("/v1/members", headers=auth("owner_seller")).json()["members"]
    owner = next(m for m in members if m["role"] == "owner")
    member = next(m for m in members if m["role"] == "member")
    r = client.delete(f"/v1/members/{owner['user_id']}", headers=auth("owner_seller"))
    assert r.status_code == 409 and r.json()["code"] == "LAST_OWNER"
    session.add(TelegramLink(chat_id=777, chat_type="private", user_id=member["user_id"], tenant_id="demo_seller"))
    session.commit()
    assert client.delete(f"/v1/members/{member['user_id']}", headers=auth("owner_seller")).status_code == 204
    session.expire_all()
    link = session.scalar(select(TelegramLink).where(TelegramLink.chat_id == 777))
    assert link.status == "revoked"
    r = client.get("/v1/tenants/demo_seller", headers=auth("member_seller"))
    assert r.status_code == 403
    # Member không quản lý được thành viên.
    assert client.get("/v1/members", headers=auth("owner_agency", "demo_seller")).status_code == 403


@pytest.mark.parametrize("key", ["member_seller", "engineer"])
def test_cannot_manage_users(client: Any, key: str) -> None:
    r = client.post(
        "/v1/members/invitations",
        json={"email": "x@example.com", "metric_allowlist": ["net_revenue"]},
        headers=auth(key, "demo_seller"),
    )
    assert r.status_code == 403
