"""Log JSON ra stdout, kèm `tenant_id`, `request_id`, `run_id` khi có (spec 00 §1.1, §3.4).

Không ghi token, khóa API, số điện thoại, email người mua hay nội dung file khách tải lên.
Bộ lọc `RedactFilter` che các mẫu dễ lộ như lưới an toàn; code gọi log vẫn phải tự tránh ghi dữ liệu đó.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:\d[\s.-]?){8,10}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+")
_SECRET_KV_RE = re.compile(r"(?i)((?:token|key|password|secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+")


def redact(text: str) -> str:
    text = _BEARER_RE.sub(r"\1***", text)
    text = _SECRET_KV_RE.sub(r"\1***", text)
    text = _EMAIL_RE.sub("***@***", text)
    return _PHONE_RE.sub("***", text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, var in (("tenant_id", tenant_id_var), ("request_id", request_id_var), ("run_id", run_id_var)):
            value = var.get()
            if value:
                payload[key] = value
        extra = getattr(record, "dx", None)
        if isinstance(extra, dict):
            payload.update({k: v for k, v in extra.items() if k not in payload})
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
