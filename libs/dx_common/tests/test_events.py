from __future__ import annotations

import pytest
from sqlalchemy import Engine

from dx_common.events import Event, consume, publish
from dx_common.events.bus import dead_letters


@pytest.mark.pg
def test_events_idempotent_consumer(events_engine: Engine) -> None:
    eid = publish("inputs.changed", "demo_seller", {"kind": "product_costs"}, "s6-portal", bind=events_engine)
    seen: list[str] = []

    def handler(ev: Event) -> None:
        seen.append(ev.event_id)

    assert consume("t1", ["inputs.changed"], handler, engine=events_engine) == 1
    # Giao lần hai (quét lại cửa sổ) không xử lý trùng.
    assert consume("t1", ["inputs.changed"], handler, engine=events_engine) == 0
    assert seen == [eid]
    # Consumer khác vẫn nhận.
    assert consume("t2", ["inputs.changed"], handler, engine=events_engine) == 1


@pytest.mark.pg
def test_publish_validates_payload(events_engine: Engine) -> None:
    with pytest.raises(ValueError):
        publish("inputs.changed", "demo_seller", {"kind": "wrong"}, "x", bind=events_engine)
    with pytest.raises(ValueError):
        publish("no.such", None, {}, "x", bind=events_engine)


@pytest.mark.pg
def test_handler_failure_retries_then_dead_letters(events_engine: Engine) -> None:
    publish("tenant.created", "demo_seller", {}, "s4", bind=events_engine)
    calls = 0

    def bad(ev: Event) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    for _ in range(6):
        consume("t3", ["tenant.created"], bad, engine=events_engine)
    assert calls == 5
    assert len(dead_letters("t3", engine=events_engine)) == 1
