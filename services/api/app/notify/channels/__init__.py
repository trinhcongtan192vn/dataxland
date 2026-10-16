"""Danh sách kênh đăng ký (spec 04 §5.1). Thêm kênh mới (ví dụ Zalo) là thêm một adapter và đăng ký ở đây,
không sửa `dispatcher.py` (FR-OPS-08).
"""

from __future__ import annotations

from app.notify.channels.email import EmailChannel
from app.notify.channels.telegram import TelegramChannel
from app.notify.types import Channel

_CHANNELS: dict[str, Channel] = {}


def _defaults() -> dict[str, Channel]:
    return {"telegram": TelegramChannel(), "email": EmailChannel()}


def registered_channels() -> dict[str, Channel]:
    if not _CHANNELS:
        _CHANNELS.update(_defaults())
    return _CHANNELS


def register_channel(channel: Channel) -> None:
    registered_channels()[channel.name] = channel


def unregister_channel(name: str) -> None:
    registered_channels().pop(name, None)


def reset_channels() -> None:
    _CHANNELS.clear()
