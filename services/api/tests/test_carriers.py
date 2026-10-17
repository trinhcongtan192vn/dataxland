"""Hãng vận chuyển (FR-ING-09): webhook GHN/GHTK, file đối soát J&T."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from tests.conftest import auth


def _url(client: Any, carrier: str) -> str:
    rows = {r["carrier"]: r for r in client.get("/v1/carriers", headers=auth("owner_seller")).json()}
    return str(rows[carrier]["webhook_url"]).split("://", 1)[1].split("/", 1)[1]


def test_fr_ing_09_webhook_stores_waybill_without_receiver(client: Any, session: Any) -> None:
    from app.db.models import CarrierEvent

    path = "/" + _url(client, "ghn")
    body = {
        "OrderCode": "GHN1",
        "ClientOrderCode": "2607180100001SP",
        "Status": "delivered",
        "Time": "2026-10-12T05:00:00Z",
        "TotalFee": 22000,
        "CODAmount": 350000,
        "ToName": "Nguyễn Văn A",
        "ToPhone": "0909123456",
        "ToAddress": "1 Lê Lợi",
    }
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json=body).json()["received"] == 0  # gửi trùng không tạo dòng mới
    ev = session.scalars(select(CarrierEvent)).one()
    assert (ev.waybill, ev.status_raw, int(ev.cod_amount or 0)) == ("GHN1", "delivered", 350000)
    assert "0909123456" not in str(ev.__dict__)
    # Sai token hoặc hãng khách chưa bật → 404.
    assert client.post(path[:-4] + "xxxx", json=body).status_code == 404
    bad = path.replace("/ghn/", "/ghtk/")
    assert client.post(bad, json={"label_id": "X", "status_id": 5}).status_code == 404
    rows = {r["carrier"]: r for r in client.get("/v1/carriers", headers=auth("owner_seller")).json()}
    assert rows["ghn"]["waybills"] == 1 and rows["jnt"]["kind"] == "file"
    # Member chỉ xem, không thấy URL webhook (có token).
    member = {r["carrier"]: r for r in client.get("/v1/carriers", headers=auth("member_seller")).json()}
    assert member["ghn"]["webhook_url"] is None


def test_fr_ing_09_upload_jnt_file(client: Any, tmp_path: Any, monkeypatch: Any) -> None:
    from dx_common.config import reset_settings_cache

    monkeypatch.setenv("METADATA_BUCKET", str(tmp_path))
    reset_settings_cache()
    try:
        h = auth("owner_seller")
        r = client.post(
            "/v1/inputs/carrier-files",
            files={"file": ("doi-soat.xlsx", b"PK\x03\x04x", "application/octet-stream")},
            headers=h,
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "received"
        bad = client.post("/v1/inputs/carrier-files", files={"file": ("a.pdf", b"x", "application/pdf")}, headers=h)
        assert bad.status_code == 400
        listed = client.get("/v1/inputs/carrier-files", headers=h).json()
        assert [f["filename"] for f in listed] == ["doi-soat.xlsx"]
        assert list(tmp_path.rglob("*.xlsx"))
        other = client.post(
            "/v1/inputs/carrier-files", files={"file": ("d.xlsx", b"x", "x")}, headers=auth("owner_agency")
        )
        assert other.status_code == 400  # demo_agency chưa bật J&T
    finally:
        reset_settings_cache()


def test_parse_ghtk_event() -> None:
    from app.routers.carriers import parse_event

    ev = parse_event(
        "ghtk",
        {
            "label_id": "S1.A1",
            "partner_id": "O1",
            "status_id": 5,
            "action_time": "2026-10-12 10:00:00",
            "fee": 30000,
            "pick_money": 200000,
            "customer_tel": "0911",
        },
    )
    assert ev["waybill"] == "S1.A1" and ev["status_raw"] == "5" and ev["event_at"].hour == 3
    assert "customer_tel" not in ev
