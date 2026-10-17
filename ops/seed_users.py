"""Tài khoản demo cho môi trường `local` (chạy trong `make seed-local`): tạo người dùng trên Firebase Auth Emulator
(email đã xác minh) và vai trò tương ứng trong Postgres, để đăng nhập cổng thử mọi vai trò.

Chỉ chạy khi `DX_ENV=local` và có `FIREBASE_AUTH_EMULATOR_HOST`. Không dùng cho `dev`/`prod`.

| Email | Vai trò |
|---|---|
| lead@dataxland.local | Trưởng nhóm data (data_lead) – vận hành, duyệt báo cáo, kết nối sàn |
| eng@dataxland.local | Kỹ sư (engineer) – xem vận hành |
| owner.seller@demo.local | Chủ shop `demo_seller` |
| member.seller@demo.local | Thành viên `demo_seller`, chỉ xem doanh thu thực nhận và số đơn |
| owner.agency@demo.local | Chủ shop `demo_agency` |
| am@agency.local | Agency `demo_partner`, được `demo_agency` cấp quyền |

Mật khẩu chung: `DataxLand@2026`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]

from dx_common.config import get_settings  # noqa: E402
from dx_common.ids import new_ulid  # noqa: E402

# Mật khẩu của tài khoản demo trên Firebase Auth Emulator (chỉ local, không phải bí mật); đổi bằng DX_DEMO_PASSWORD.
PASSWORD = os.environ.get("DX_DEMO_PASSWORD", "DataxLand@2026")
USERS: list[dict[str, Any]] = [
    {"email": "lead@dataxland.local", "name": "Trưởng nhóm data", "staff_role": "data_lead"},
    {"email": "eng@dataxland.local", "name": "Kỹ sư dữ liệu", "staff_role": "engineer"},
    {"email": "owner.seller@demo.local", "name": "Chủ Shop Demo", "memberships": [("demo_seller", "owner", None)]},
    {
        "email": "member.seller@demo.local",
        "name": "Nhân viên Shop Demo",
        "memberships": [("demo_seller", "member", ["net_revenue", "order_count"])],
    },
    {"email": "owner.agency@demo.local", "name": "Chủ Brand Demo", "memberships": [("demo_agency", "owner", None)]},
    {"email": "am@agency.local", "name": "AM Agency Demo", "partner": "demo_partner"},
]


def emulator_user(host: str, project: str, email: str, name: str) -> str:
    """Tạo (hoặc lấy) người dùng trên emulator, đánh dấu đã xác minh email. Trả `localId`."""
    base = f"http://{host}/identitytoolkit.googleapis.com/v1"
    with httpx.Client(timeout=10) as c:
        r = c.post(
            f"{base}/accounts:signUp?key=local", json={"email": email, "password": PASSWORD, "displayName": name}
        )
        if r.status_code == 200:
            uid = str(r.json()["localId"])
        else:
            r = c.post(
                f"{base}/accounts:signInWithPassword?key=local",
                json={"email": email, "password": PASSWORD, "returnSecureToken": True},
            )
            r.raise_for_status()
            uid = str(r.json()["localId"])
        c.post(
            f"{base}/projects/{project}/accounts:update",
            headers={"Authorization": "Bearer owner"},
            json={"localId": uid, "emailVerified": True, "displayName": name},
        ).raise_for_status()
    return uid


def seed_demo_users() -> str:
    s = get_settings()
    if not s.is_local or not s.firebase_auth_emulator_host:
        return "bỏ qua tài khoản demo: chỉ chạy ở local với Firebase Auth Emulator"
    from sqlalchemy import text

    from dx_common.db import get_engine

    eng = get_engine()
    with eng.begin() as conn:
        have = {r[0] for r in conn.execute(text("select tenant_id from tenants"))}
        if not {"demo_seller", "demo_agency"} <= have:
            return "bỏ qua tài khoản demo: chưa có khách trong Postgres (chạy `make sync-tenants` trước)"
        for u in USERS:
            uid = emulator_user(s.firebase_auth_emulator_host, s.firebase_project_id, u["email"], u["name"])
            row = conn.execute(text("select id from users where email = :e"), {"e": u["email"]}).first()
            user_id = row[0] if row else new_ulid()
            if row:
                conn.execute(
                    text(
                        "update users set firebase_uid = :f, display_name = :n, staff_role = :s,"
                        " disabled = false, updated_at = now() where id = :id"
                    ),
                    {"f": uid, "n": u["name"], "s": u.get("staff_role"), "id": user_id},
                )
            else:
                conn.execute(
                    text(
                        "insert into users (id, firebase_uid, email, display_name, staff_role, disabled,"
                        " created_at, updated_at) values (:id, :f, :e, :n, :s, false, now(), now())"
                    ),
                    {"id": user_id, "f": uid, "e": u["email"], "n": u["name"], "s": u.get("staff_role")},
                )
            for tid, role, allow in u.get("memberships", []):
                conn.execute(
                    text("delete from memberships where user_id = :u and tenant_id = :t"), {"u": user_id, "t": tid}
                )
                conn.execute(
                    text(
                        "insert into memberships (id, user_id, tenant_id, role, metric_allowlist,"
                        " created_at, updated_at) values (:id, :u, :t, :r, :a, now(), now())"
                    ),
                    {"id": new_ulid(), "u": user_id, "t": tid, "r": role, "a": allow},
                )
            if u.get("partner"):
                pid = u["partner"]
                conn.execute(
                    text(
                        "insert into partner_users (user_id, partner_id, created_at, updated_at)"
                        " values (:u, :p, now(), now()) on conflict do nothing"
                    ),
                    {"u": user_id, "p": pid},
                )
                exists = conn.execute(
                    text(
                        "select 1 from partner_grants where tenant_id = 'demo_agency' and"
                        " partner_id = :p and revoked_at is null"
                    ),
                    {"p": pid},
                ).first()
                if not exists:
                    conn.execute(
                        text(
                            "insert into partner_grants (id, tenant_id, partner_id, granted_by, granted_at,"
                            " created_at, updated_at) values (:id, 'demo_agency', :p, 'seed', now(), now(),"
                            " now())"
                        ),
                        {"id": new_ulid(), "p": pid},
                    )
    return f"tài khoản demo: {len(USERS)} người dùng, mật khẩu {PASSWORD}"


if __name__ == "__main__":
    print(seed_demo_users())
    sys.exit(0)
