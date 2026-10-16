"""FR-ING-07 (spec 01 §11): đơn `COMPLETED` ở lần 1, đổi trạng thái ở lần 2 → raw có trạng thái mới."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from connectors.shopee.source import sync_shopee
from connectors.shopee.tests.test_source import NOW, _ctx, make_env


@pytest.fixture()
def env(tmp_path: Path) -> Iterator[dict[str, Any]]:
    yield from make_env(tmp_path)


def _status(env: dict[str, Any], sn: str) -> str:
    rows = env["wh"].query(
        'select order_status from "t_demo_seller_raw"."shopee__orders" where order_sn = ? order by _dx_loaded_at desc',
        [sn],
    )
    return str(rows[0][0])


def test_fr_ing_07_status_change_after_delivery(env: dict[str, Any]) -> None:
    sn = "2610100100001SP"
    with env["fake"].mock():
        sync_shopee(env["tenant"], env["source"], _ctx(env))
    assert _status(env, sn) == "COMPLETED"
    # Người mua trả hàng sau khi đã giao: nguồn cập nhật trạng thái và update_time.
    env["fake"].set_status(sn, "TO_RETURN", int((NOW + timedelta(hours=3)).timestamp()))
    with env["fake"].mock():
        sync_shopee(env["tenant"], env["source"], _ctx(env, NOW + timedelta(hours=6)))
    assert _status(env, sn) == "TO_RETURN"
