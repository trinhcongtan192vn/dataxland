"""Đọc file khách tải lên (spec 07 §4.2): xlsx (openpyxl, read_only) và csv (tự nhận mã hóa, dấu phân cách).
Nhận diện loại file theo tiêu đề cột (`signatures.yml`)."""

from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dx_common.timeutil import VN_TZ

MATCH_RATIO = 0.8
MAX_ROWS = 500_000


class FileError(Exception):
    def __init__(self, code: str, message_vi: str) -> None:
        super().__init__(code)
        self.code, self.message_vi = code, message_vi


@dataclass
class Table:
    headers: list[str]
    rows: list[dict[str, Any]]


def norm(s: str) -> str:
    """So khớp tiêu đề không phân biệt hoa thường, dấu cách thừa, dạng Unicode."""
    return " ".join(unicodedata.normalize("NFC", str(s)).strip().lower().split())


@cache
def signatures() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load((Path(__file__).parent / "signatures.yml").read_text(encoding="utf-8"))
    return dict(data)


def label(kind: str) -> str:
    return str(signatures().get(kind, {}).get("label_vi", kind))


def score(kind: str, headers: list[str]) -> tuple[float, list[str]]:
    have = {norm(h) for h in headers}
    groups: list[list[str]] = signatures()[kind]["columns"]
    missing = [g[0] for g in groups if not any(norm(c) in have for c in g)]
    return 1 - len(missing) / len(groups), missing


def detect(headers: list[str]) -> str | None:
    best = max(((score(k, headers)[0], k) for k in signatures()), default=(0.0, ""))
    return best[1] if best[0] >= MATCH_RATIO else None


def _decode(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1258", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise FileError("ENCODING", "Không đọc được mã hóa của file")


def read_csv(raw: bytes) -> Table:
    text = _decode(raw)
    first = text.split("\n", 1)[0]
    delim = max((",", ";", "\t"), key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise FileError("EMPTY", "File trống")
    headers = [h.strip() for h in rows[0]]
    return Table(headers, [dict(zip(headers, r, strict=False)) for r in rows[1 : MAX_ROWS + 1]])


def read_xlsx(raw: bytes) -> Table:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise FileError("XLSX_INVALID", "File Excel bị lỗi hoặc có mật khẩu") from exc
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    headers: list[str] = []
    for row in it:  # bỏ dòng trống đầu file
        if row and any(c not in (None, "") for c in row):
            headers = [str(c).strip() if c is not None else "" for c in row]
            break
    if not headers:
        raise FileError("EMPTY", "File trống")
    rows: list[dict[str, Any]] = []
    for row in it:
        if row is None or all(c in (None, "") for c in row):
            continue
        rows.append(dict(zip(headers, row, strict=False)))
        if len(rows) >= MAX_ROWS:
            break
    wb.close()
    return Table(headers, rows)


def read_table(raw: bytes, filename: str) -> Table:
    name = filename.lower()
    if name.endswith(".csv"):
        return read_csv(raw)
    if name.endswith(".xlsx"):
        return read_xlsx(raw)
    raise FileError("EXTENSION", "Chỉ nhận file .xlsx hoặc .csv")


class Row:
    """Truy cập một dòng theo nhóm tên cột trong `signatures.yml`."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = {norm(k): v for k, v in data.items()}

    def get(self, *names: str) -> Any:
        for n in names:
            v = self.data.get(norm(n))
            if v not in (None, ""):
                return v
        return None


def to_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    return s or None


def to_num(v: Any) -> Decimal | None:
    """`120000`, `120.000`, `120,000`, `-35,840.50`, `(1.000)` → Decimal."""
    if v is None or v == "":
        return None
    if isinstance(v, int | float | Decimal):
        return Decimal(str(v))
    s = str(v).strip().replace(" ", "").replace("₫", "").replace("đ", "").replace("VND", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(",", ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.lstrip("-").split(sep)
        s = s.replace(sep, "") if all(len(p) == 3 for p in parts[1:]) and len(parts) > 1 else s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return -d if neg else d


def to_int(v: Any) -> int | None:
    d = to_num(v)
    return None if d is None else int(d)


DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y")
DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
)


def to_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:10]
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def to_utc(v: Any) -> datetime | None:
    """Thời điểm trong file là giờ Việt Nam → UTC (không kèm múi giờ, như mọi timestamp lưu trong kho)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        s = str(v).strip()
        dt = None
        for f in DATETIME_FORMATS:
            try:
                dt = datetime.strptime(s, f)
                break
            except ValueError:
                continue
        if dt is None:
            d = to_date(s)
            if d is None:
                return None
            dt = datetime(d.year, d.month, d.day)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(UTC).replace(tzinfo=None)
