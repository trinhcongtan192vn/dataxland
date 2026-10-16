"""Dựng tin từ mẫu có phiên bản (spec 04 §5.2).

`templates/<name>/meta.yml` có `version`, `audience`, `channels`, `title`; mỗi mẫu có `telegram.html.j2`,
`email.html.j2`, `email.txt.j2` (mẫu chỉ dùng cho bot có thể chỉ có bản Telegram). Mọi kênh dùng cùng dữ liệu
đầu vào. Dữ liệu đầu vào chỉ gồm số tổng hợp và link, không có thông tin người mua (FR-TG-08).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.notify.types import Button, RenderedMessage
from dx_common.money import format_vnd
from dx_common.timeutil import format_as_of, format_week_label, to_vn

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _num_vi(v: float, digits: int = 1) -> str:
    s = f"{abs(v):,.{digits}f}"
    s = s.replace(",", "§").replace(".", ",").replace("§", ".")
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def f_pct(v: Any, digits: int = 1) -> str:
    if v is None:
        return "—"
    x = float(v)
    return ("−" if x < 0 else "") + _num_vi(x * 100, digits) + "%"


def f_change(v: Any) -> str:
    if v is None:
        return "—"
    x = float(v)
    if x == 0:
        return "0%"
    return ("▲ " if x > 0 else "▼ ") + _num_vi(abs(x) * 100, 1) + "%"


def f_ratio(v: Any) -> str:
    if v is None:
        return "—"
    x = float(v)
    return ("−" if x < 0 else "") + _num_vi(x, 1) + "x"


def f_count(v: Any) -> str:
    if v is None:
        return "—"
    return f"{int(round(float(v))):,}".replace(",", ".")


def f_unit(v: Any, unit: str) -> str:
    if unit == "VND":
        return format_vnd(v if v is None else Decimal(str(v)))
    if unit == "percent":
        return f_pct(v)
    if unit == "ratio":
        return f_ratio(v)
    return f_count(v)


def f_date(v: Any) -> str:
    if v is None:
        return "—"
    d = date.fromisoformat(v) if isinstance(v, str) else v
    return d.strftime("%d/%m/%Y")


def f_short_date(v: Any) -> str:
    d = date.fromisoformat(v) if isinstance(v, str) else v
    return d.strftime("%d/%m")


def f_as_of(v: Any) -> str:
    if not v:
        return "—"
    ts = datetime.fromisoformat(v.replace("Z", "+00:00")) if isinstance(v, str) else v
    return format_as_of(ts)


def f_datetime(v: Any) -> str:
    if not v:
        return "—"
    ts = datetime.fromisoformat(v.replace("Z", "+00:00")) if isinstance(v, str) else v
    return to_vn(ts).strftime("%H:%M %d/%m/%Y")


def f_week(v: Any) -> str:
    d = date.fromisoformat(v) if isinstance(v, str) else v
    return format_week_label(d)


def _env(autoescape: bool) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]) if autoescape else False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    env.filters.update(
        vnd=lambda v: format_vnd(v if v is None else Decimal(str(v))),
        pct=f_pct,
        change=f_change,
        ratio=f_ratio,
        count=f_count,
        unit=f_unit,
        date_vn=f_date,
        short_date=f_short_date,
        as_of=f_as_of,
        datetime_vn=f_datetime,
        week=f_week,
    )
    return env


@lru_cache(maxsize=2)
def env(autoescape: bool) -> Environment:
    return _env(autoescape)


@lru_cache(maxsize=64)
def meta(name: str) -> dict[str, Any]:
    p = TEMPLATES_DIR / name / "meta.yml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"meta.yml lỗi: {name}")
    return data


def template_names() -> list[str]:
    return sorted(p.parent.name for p in TEMPLATES_DIR.glob("*/meta.yml"))


def render(name: str, data: dict[str, Any], buttons: list[Button] | None = None) -> RenderedMessage:
    m = meta(name)
    folder = TEMPLATES_DIR / name
    ctx = {**data, "buttons": [b.__dict__ for b in (buttons or [])]}
    title = env(False).from_string(str(m.get("title", name))).render(**ctx).strip()
    tg = (
        env(True).get_template(f"{name}/telegram.html.j2").render(**ctx).strip()
        if (folder / "telegram.html.j2").exists()
        else None
    )
    html = (
        env(True).get_template(f"{name}/email.html.j2").render(**ctx).strip()
        if (folder / "email.html.j2").exists()
        else None
    )
    if (folder / "email.txt.j2").exists():
        text = env(False).get_template(f"{name}/email.txt.j2").render(**ctx).strip()
    else:
        text = _strip_tags(tg or title)
    return RenderedMessage(
        title=title,
        text=text,
        telegram_html=tg,
        email_html=html,
        buttons=list(buttons or []),
        template=name,
        template_version=str(m.get("version", "1")),
    )


def _strip_tags(html: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", html)
