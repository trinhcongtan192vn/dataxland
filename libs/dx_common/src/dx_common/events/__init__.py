"""Sự kiện theo mẫu outbox trong Postgres (spec 04 §4). GĐ2 thay bằng Pub/Sub, giữ chữ ký hai hàm."""

from dx_common.events.bus import Event, consume, publish
from dx_common.events.schemas import EVENT_TYPES, payload_model
from dx_common.events.tables import metadata as events_metadata

__all__ = ["EVENT_TYPES", "Event", "consume", "events_metadata", "payload_model", "publish"]
