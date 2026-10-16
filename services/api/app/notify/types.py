"""Kiểu dữ liệu của lớp thông báo (spec 04 §5.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

RecipientKind = Literal["user", "team", "telegram_chat", "email"]


@dataclass(frozen=True)
class Recipient:
    kind: RecipientKind
    address: str
    tenant_id: str | None = None
    scope: tuple[str, ...] | None = None  # phạm vi chỉ số của liên kết nhóm Telegram
    user_id: str | None = None
    telegram_link_id: str | None = None

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.address}"


@dataclass(frozen=True)
class Button:
    label: str
    url: str | None = None
    callback_data: str | None = None


@dataclass
class RenderedMessage:
    """Tiêu đề, thân văn bản, các nút. Mỗi kênh dùng bản phù hợp với định dạng của mình."""

    title: str
    text: str
    telegram_html: str | None = None
    email_html: str | None = None
    buttons: list[Button] = field(default_factory=list)
    template: str = ""
    template_version: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "title": self.title,
            "text": self.text,
            "telegram_html": self.telegram_html,
            "email_html": self.email_html,
            "buttons": [{"label": b.label, "url": b.url, "callback_data": b.callback_data} for b in self.buttons],
            "template": self.template,
            "template_version": self.template_version,
        }

    @classmethod
    def from_json(cls, d: dict[str, object]) -> RenderedMessage:
        raw_buttons = d.get("buttons") or []
        buttons = [
            Button(label=str(b["label"]), url=b.get("url"), callback_data=b.get("callback_data"))  # type: ignore[index,union-attr,arg-type]
            for b in raw_buttons  # type: ignore[union-attr]
        ]
        return cls(
            title=str(d.get("title", "")),
            text=str(d.get("text", "")),
            telegram_html=d.get("telegram_html"),  # type: ignore[arg-type]
            email_html=d.get("email_html"),  # type: ignore[arg-type]
            buttons=buttons,
            template=str(d.get("template", "")),
            template_version=str(d.get("template_version", "")),
        )


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    error_code: str | None = None
    retryable: bool = True
    connection_error: bool = False


@runtime_checkable
class Channel(Protocol):
    name: str

    def supports(self, recipient: Recipient) -> bool: ...

    async def send(self, recipient: Recipient, message: RenderedMessage) -> DeliveryResult: ...
