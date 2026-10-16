"""Gửi một tin ngay, không qua sự kiện (lời mời thành viên, email xác nhận kiểm tra sức khỏe).

Vẫn đi qua adapter kênh đã đăng ký, nên dùng chung định dạng và cấu hình với trung tâm thông báo.
"""

from __future__ import annotations

import asyncio

from app.notify.channels import registered_channels
from app.notify.render import render
from app.notify.types import Button, DeliveryResult, Recipient
from dx_common.logging import get_logger

log = get_logger(__name__)


def send_email_now(
    to: str, template: str, data: dict[str, object], buttons: list[Button] | None = None
) -> DeliveryResult:
    msg = render(template, data, buttons)
    channel = registered_channels().get("email")
    if channel is None:
        return DeliveryResult(ok=False, error_code="EMAIL_CHANNEL_MISSING")
    try:
        result = asyncio.run(channel.send(Recipient(kind="email", address=to), msg))
    except RuntimeError:
        # Đang ở trong event loop (hiếm): chạy trên loop mới ở luồng khác.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            result = ex.submit(lambda: asyncio.run(channel.send(Recipient(kind="email", address=to), msg))).result()
    if not result.ok:
        log.warning("gửi email %s lỗi: %s", template, result.error_code)
    return result
