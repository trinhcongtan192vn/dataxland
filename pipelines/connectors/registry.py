"""Chọn connector cho một nguồn (spec 01 §2). Thêm nguồn mới là thêm một dòng ở `DLT_CONNECTORS`."""

from __future__ import annotations

import importlib
from collections.abc import Callable

from connectors.base import Connector
from dx_common.config import Settings, get_settings
from dx_common.secrets import get_secret_store
from dx_common.tenants import SourceConfig

# type → "module:hàm"
DLT_CONNECTORS: dict[str, str] = {
    "portal": "connectors.portal:sync_portal",
    "shopee": "connectors.shopee.source:sync_shopee",
    "tiktok_shop": "connectors.tiktok_shop.source:sync_tiktok_shop",
    "lazada": "connectors.lazada.source:sync_lazada",
    "ghn": "connectors.carriers.ghn:sync_ghn",
    "ghtk": "connectors.carriers.ghtk:sync_ghtk",
    "jnt": "connectors.carriers.jnt:sync_jnt",
}


def _load(path: str) -> Connector:
    mod, _, fn = path.partition(":")
    f: Callable[..., object] = getattr(importlib.import_module(mod), fn)
    return f  # type: ignore[return-value]


def connector_for(source: SourceConfig, settings: Settings | None = None) -> Connector | None:
    """Trả connector cần chạy; None với nguồn Windsor (DataxLand không chạy code nạp, spec 01 §8)."""
    s = settings or get_settings()
    if source.connector == "windsor":
        return None
    if source.type == "portal":
        return _load(DLT_CONNECTORS["portal"])
    if source.type == "jnt":  # file đối soát, không cần secret (ADR 0005)
        return _load(DLT_CONNECTORS["jnt"])
    if s.is_local and (not source.secret_ref or not get_secret_store(s).exists(source.secret_ref)):
        return _load("connectors.samples:sync_from_samples")
    path = DLT_CONNECTORS.get(source.type)
    if path is None:
        raise ValueError(f"chưa có connector cho {source.type}")
    return _load(path)
