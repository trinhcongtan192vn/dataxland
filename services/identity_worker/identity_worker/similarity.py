"""Chặn khối và điểm độ giống cho gợi ý ghép sản phẩm (spec 10 §4 bước 1–2)."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from rapidfuzz import fuzz

from identity_worker.candidates import Product

STOPWORDS = {
    "chinh",
    "hang",
    "chinhhang",
    "freeship",
    "free",
    "ship",
    "sale",
    "hot",
    "new",
    "moi",
    "gia",
    "re",
    "tot",
    "cao",
    "cap",
    "loai",
    "1",
    "combo",
    "set",
    "hop",
    "chai",
    "tuyp",
    "goi",
    "mau",
    "san",
    "pham",
    "chat",
    "luong",
    "official",
    "store",
    "genuine",
    "auth",
    "authentic",
    "hcm",
    "hn",
}
SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l|g|kg|mg|cm|mm|vien|goi|mieng)\b")
COLORS = {"do", "den", "trang", "xanh", "vang", "hong", "tim", "nau", "xam", "cam", "be"}
TOP_K = 5


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm_name(name: str | None) -> str:
    s = strip_accents(name or "").lower()
    s = re.sub(r"[^a-z0-9.,\s]", " ", s)
    return " ".join(s.split())


def keywords(name: str | None) -> set[str]:
    n = SIZE_RE.sub(" ", norm_name(name))
    return {w for w in n.split() if len(w) > 1 and w not in STOPWORDS and not w.isdigit()}


def attributes(name: str | None) -> set[str]:
    n = norm_name(name)
    out = {f"{float(v.replace(',', '.')):g}{u}" for v, u in SIZE_RE.findall(n)}
    out |= {f"color:{w}" for w in n.split() if w in COLORS}
    return out


def price_gap(a: float | None, b: float | None) -> float | None:
    if not a or not b:
        return None
    return abs(a - b) / max(a, b)


def sim_score(a: Product, b: Product) -> float:
    """0,6 × token_set_ratio tên + 0,3 × trùng thuộc tính + 0,1 × (1 − lệch giá)."""
    name = fuzz.token_set_ratio(norm_name(a.name), norm_name(b.name)) / 100
    aa, ab = attributes(a.name), attributes(b.name)
    attr = (len(aa & ab) / len(aa | ab)) if (aa or ab) else 0.5
    gap = price_gap(a.price, b.price)
    price = 1 - min(gap, 1.0) if gap is not None else 0.5
    return round(0.6 * name + 0.3 * attr + 0.1 * price, 4)


def candidate_pairs(products: list[Product], exclude: set[str] | None = None) -> list[tuple[Product, Product, float]]:
    """Cặp khác kênh, giá lệch ≤ 50%, có ít nhất một từ khóa chung; tối đa 5 ứng viên tốt nhất mỗi sản phẩm."""
    exclude = exclude or set()
    index: dict[str, list[int]] = defaultdict(list)
    kws = [keywords(p.name) for p in products]
    for i, ks in enumerate(kws):
        for k in ks:
            index[k].append(i)
    best: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for i, p in enumerate(products):
        seen: set[int] = set()
        for k in kws[i]:
            for j in index[k]:
                if j <= i or j in seen:
                    continue
                seen.add(j)
                q = products[j]
                if q.source == p.source:
                    continue
                gap = price_gap(p.price, q.price)
                if gap is not None and gap > 0.5:
                    continue
                pair_key = "|".join(sorted((p.key, q.key)))
                if pair_key in exclude:
                    continue
                s = sim_score(p, q)
                best[i].append((s, j))
                best[j].append((s, i))
    out: dict[tuple[int, int], float] = {}
    for i, lst in best.items():
        for s, j in sorted(lst, reverse=True)[:TOP_K]:
            out[tuple(sorted((i, j)))] = s  # type: ignore[index]
    return [(products[i], products[j], s) for (i, j), s in sorted(out.items(), key=lambda x: -x[1])]
