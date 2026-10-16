"""Tiền VND (spec 00 §3.3): API trả số nguyên làm tròn đến đồng; hiển thị `1.234.567 ₫`."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def round_vnd(value: Decimal | float | int | str | None) -> int | None:
    if value is None:
        return None
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _group(n: int, sep: str) -> str:
    s = f"{abs(n):,}".replace(",", sep)
    return f"-{s}" if n < 0 else s


def format_vnd(value: Decimal | float | int | None) -> str:
    v = round_vnd(value)
    if v is None:
        return "—"
    s = _group(v, ".")
    return s.replace("-", "−") + " ₫"


def format_foreign(value: Decimal | float | str, currency: str = "USD") -> str:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    symbol = {"USD": "$"}.get(currency, currency + " ")
    sign = "-" if d < 0 else ""
    return f"{sign}{symbol}{abs(d):,.2f}"


def parse_vnd_text(text: str) -> Decimal:
    """Nhận `120000`, `120.000`, `120,000` (spec 05 §6.4). Lỗi thì ném ValueError."""
    raw = text.strip().replace(" ", "").replace("₫", "").replace("đ", "")
    if not raw:
        raise ValueError("empty")
    if "." in raw and "," in raw:
        raise ValueError("ambiguous")
    for sep in (".", ","):
        if sep in raw:
            parts = raw.split(sep)
            if all(p.isdigit() for p in parts) and all(len(p) == 3 for p in parts[1:]):
                raw = "".join(parts)
            elif len(parts) == 2 and parts[0].lstrip("-").isdigit() and parts[1].isdigit():
                raw = parts[0] + "." + parts[1]
            else:
                raise ValueError("invalid")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("invalid") from exc
