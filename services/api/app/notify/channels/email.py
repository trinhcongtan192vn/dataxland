"""Kênh email qua SMTP, gửi kèm bản HTML và văn bản thuần (spec 04 §5.1)."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from app.notify.types import DeliveryResult, Recipient, RenderedMessage
from dx_common.config import get_settings
from dx_common.logging import get_logger

log = get_logger(__name__)


def _send_sync(to: str, subject: str, text: str, html: str | None) -> None:
    s = get_settings()
    if not s.smtp_host:
        raise ConnectionError("SMTP_HOST chưa cấu hình")
    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="dataxland.vn")
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


class EmailChannel:
    name = "email"

    def supports(self, recipient: Recipient) -> bool:
        return recipient.kind in ("email", "team") and "@" in recipient.address

    async def send(self, recipient: Recipient, message: RenderedMessage) -> DeliveryResult:
        try:
            await asyncio.to_thread(_send_sync, recipient.address, message.title, message.text, message.email_html)
        except (ConnectionError, OSError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as exc:
            log.warning("email lỗi kết nối: %s", type(exc).__name__)
            return DeliveryResult(ok=False, error_code="SMTP_CONNECTION", connection_error=True)
        except smtplib.SMTPRecipientsRefused:
            return DeliveryResult(ok=False, error_code="SMTP_RECIPIENT_REFUSED", retryable=False)
        except smtplib.SMTPException as exc:
            return DeliveryResult(ok=False, error_code=f"SMTP_{type(exc).__name__}")
        return DeliveryResult(ok=True)
