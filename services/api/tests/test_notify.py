"""Trung tâm thông báo – FR-OPS-05, FR-OPS-08, NFR-12, spec 04 §5, FR-TG-08."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.notify import dispatcher
from app.notify.channels import register_channel
from app.notify.render import TEMPLATES_DIR, render, template_names
from dx_common.events import Event, consume, publish
from dx_common.timeutil import now_utc
from tests.conftest import FakeChannel


@pytest.fixture(autouse=True)
def _drain(session: Any, channels: dict[str, FakeChannel]) -> None:
    """Xả các sự kiện do fixture tạo (đăng ký khách) để mỗi test chỉ đếm tin của mình."""
    from app.db.models import Notification

    _run(session)
    session.query(Notification).delete()
    session.commit()
    for c in channels.values():
        c.sent.clear()


def _run(session: Any) -> dict[str, int]:
    """Một vòng worker trong transaction của test."""

    def handler(ev: Event) -> None:
        dispatcher.handle_event(session, ev)

    consume(dispatcher.CONSUMER, dispatcher.EVENT_TYPES, handler, engine=session.get_bind())
    stats = dispatcher.deliver_pending(session)
    session.commit()
    return stats


def test_fr_ops_05_team_alert_within_window(session: Any, channels: dict[str, FakeChannel]) -> None:
    from app.db.models import Notification

    publish(
        "sync.failed",
        "demo_seller",
        {"run_id": "r1", "source": "shopee", "reason": "auth_revoked", "detail": "refresh token hết hạn"},
        "s1-core",
        bind=session,
    )
    session.commit()
    stats = _run(session)
    rows = session.scalars(select(Notification)).all()
    assert {(n.channel, n.audience, n.status) for n in rows} == {
        ("email", "team", "sent"),
        ("telegram", "team", "sent"),
    }
    assert stats["sent"] == 2
    tg = channels["telegram"].sent[0][1]
    assert "Đồng bộ lỗi" in tg.telegram_html and "shopee" in tg.telegram_html
    assert channels["email"].sent[0][0].address == "team@dataxland.test"
    # Gộp: cùng (tenant, type, reason) trong 6 giờ không gửi thêm.
    publish(
        "sync.failed",
        "demo_seller",
        {"run_id": "r2", "source": "shopee", "reason": "auth_revoked"},
        "s1-core",
        bind=session,
    )
    session.commit()
    _run(session)
    assert len(channels["telegram"].sent) == 1


def test_test_failed_message_lists_day_source_gap(session: Any, channels: dict[str, FakeChannel]) -> None:
    publish(
        "test.failed",
        "demo_seller",
        {
            "run_id": "r9",
            "failures": [
                {
                    "test": "reconcile_daily_totals_shopee",
                    "severity": "error",
                    "rows": [
                        {
                            "source": "shopee",
                            "date": "2026-10-14",
                            "metric": "gross_amount",
                            "expected": 52000000,
                            "actual": 50500000,
                            "diff_pct": 2.9,
                        }
                    ],
                }
            ],
        },
        "s1-core",
        bind=session,
    )
    session.commit()
    _run(session)
    text = channels["email"].sent[0][1].text
    assert "shopee 14/10/2026 gross_amount: nguồn 52.000.000, kho 50.500.000, lệch 2.9%" in text


def test_fr_ops_08_fake_channel_adapter(session: Any, channels: dict[str, FakeChannel]) -> None:
    zalo = FakeChannel("zalo")
    register_channel(zalo)  # không sửa dispatcher.py
    publish("sync.failed", "demo_agency", {"source": "windsor", "reason": "windsor_stale"}, "s1-core", bind=session)
    session.commit()
    _run(session)
    assert zalo.sent, "adapter mới phải nhận tin qua giao diện chung"
    assert zalo.sent[0][1].title.startswith("[DataxLand] Đồng bộ lỗi")


def test_nfr_12_email_sent_when_telegram_down(session: Any, channels: dict[str, FakeChannel], people: Any) -> None:
    from app.db.models import ChannelHealth, Notification, Report

    channels["telegram"].fail = True
    channels["telegram"].connection_error = True
    report = Report(
        tenant_id="demo_seller",
        pack="seller",
        period_start=now_utc().date() - timedelta(days=10),
        period_end=now_utc().date() - timedelta(days=4),
        status="approved",
        built_at=now_utc(),
        insight_md="ok",
        snapshot={
            "key_numbers": {
                "numbers": [
                    {
                        "key": "net_revenue",
                        "label_vi": "Doanh thu thực nhận",
                        "value": 152340000,
                        "unit": "VND",
                        "change_pct": 0.087,
                    }
                ]
            }
        },
    )
    session.add(report)
    session.flush()
    from app.db.models import TelegramLink, User

    owner = session.scalar(select(User).where(User.email == "owner@demo-seller.example"))
    session.add(TelegramLink(chat_id=4242, chat_type="private", user_id=owner.id, tenant_id="demo_seller"))
    publish("report.ready", "demo_seller", {"report_id": report.id, "period": "2026-W41"}, "s6-portal", bind=session)
    session.commit()
    _run(session)
    emails = [r.address for r, _ in channels["email"].sent]
    assert "owner@demo-seller.example" in emails
    body = channels["email"].sent[0][1]
    assert "Doanh thu thực nhận: 152.340.000 ₫ (▲ 8,7%)" in body.text
    assert re.search(r"https://app\.test/r/[A-Za-z0-9_-]{20,}", body.text)
    tg = session.scalar(select(Notification).where(Notification.channel == "telegram"))
    assert tg.status == "pending" and tg.attempts == 1  # sẽ thử lại sau 1 phút
    # Hết 3 lần thử lại → failed; báo cáo partially_sent; sau 30 phút lỗi kết nối → email cho team.
    t0 = now_utc()
    for delay in (1, 6, 21):
        dispatcher.deliver_pending(session, now=t0 + timedelta(minutes=delay))
        session.commit()
    session.expire_all()
    assert tg.status == "failed" and tg.attempts == 4
    assert session.get(Report, report.id).status == "partially_sent"
    assert session.get(ChannelHealth, "telegram").alerted_at is None
    # Một tin Telegram khác vẫn lỗi kết nối sau 30 phút → báo team qua email.
    publish("sync.failed", "demo_seller", {"source": "lazada", "reason": "api_error"}, "s1-core", bind=session)
    session.commit()
    consume(
        dispatcher.CONSUMER,
        dispatcher.EVENT_TYPES,
        lambda ev: dispatcher.handle_event(session, ev),
        engine=session.get_bind(),
    )
    session.query(type(tg)).filter(type(tg).status == "pending").update({"next_attempt_at": t0})
    dispatcher.deliver_pending(session, now=t0 + timedelta(minutes=40))
    session.commit()
    assert session.get(ChannelHealth, "telegram").alerted_at is not None
    dispatcher.deliver_pending(session, now=t0 + timedelta(minutes=41))
    session.commit()
    assert any("Telegram không gửi được" in m.title for _, m in channels["email"].sent)


def test_anomaly_goes_to_customer_and_team(session: Any, channels: dict[str, FakeChannel], people: Any) -> None:
    publish(
        "metric.anomaly",
        "demo_seller",
        {
            "metric": "net_revenue",
            "version": "1.0.0",
            "grain": "day",
            "period": "2026-10-15",
            "value": 1000,
            "baseline": 2000,
            "diff_pct": -0.5,
            "direction": "bad",
        },
        "s2-metrics",
        bind=session,
    )
    session.commit()
    _run(session)
    to = {r.address for r, _ in channels["email"].sent}
    assert {"team@dataxland.test", "owner@demo-seller.example"} <= to


def test_fr_tg_08_no_buyer_pii_in_templates() -> None:
    names = template_names()
    assert "report_ready" in names and "bot_key_numbers" in names
    var_re = re.compile(r"{{\s*([a-zA-Z_][\w.]*)")
    for path in TEMPLATES_DIR.rglob("*.j2"):
        for var in var_re.findall(path.read_text(encoding="utf-8")):
            low = var.lower()
            assert not any(w in low for w in ("phone", "email", "address", "buyer")), (path, var)


@pytest.mark.parametrize("name", ["report_ready", "sync_failed", "test_failed", "anomaly", "tenant_event"])
def test_templates_have_versions(name: str) -> None:
    from app.notify.render import meta

    assert meta(name)["version"]
    assert (TEMPLATES_DIR / name / "telegram.html.j2").exists()


def test_report_ready_template_matches_spec() -> None:
    msg = render(
        "report_ready",
        {
            "tenant_name": "Shop Demo",
            "week_no": 41,
            "week_range": "06/10–12/10",
            "summary_only": False,
            "report_url": "https://app.dataxland.vn/r/x",
            "numbers": [
                {"label_vi": "Doanh thu thực nhận", "value": 152340000, "unit": "VND", "change_pct": 0.087},
                {"label_vi": "Lãi sau phí", "value": 18200000, "unit": "VND", "change_pct": -0.094},
                {"label_vi": "Lãi so với tuần trước", "value": -0.094, "unit": "percent", "change_pct": None},
            ],
        },
    )
    assert msg.title == "Báo cáo tuần 41 – Shop Demo"
    assert "📊 <b>Báo cáo tuần 41 (06/10–12/10) – Shop Demo</b>" in msg.telegram_html
    assert "Doanh thu thực nhận: 152.340.000 ₫ (▲ 8,7%)" in msg.telegram_html
    assert "Lãi sau phí: 18.200.000 ₫ (▼ 9,4%)" in msg.telegram_html
    assert "Lãi so với tuần trước: −9,4%" in msg.telegram_html
