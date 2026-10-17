"""Nạp `semantic/dist/metrics.json` lúc khởi động (spec 03 §4). File này do `semantic/build.py` sinh ra."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dx_common.tenants import TenantConfig


def repo_root() -> Path:
    env = os.environ.get("DX_REPO_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class MetricDef:
    metric: str
    name_vi: str
    description_vi: str
    version: str
    type: str
    unit: str
    good_direction: str
    packs: tuple[str, ...]
    hidden: bool
    requires: tuple[str, ...]
    dimensions: tuple[str, ...]
    time_grains: tuple[str, ...]
    mode: str  # "cube": một measure Cube; "engine": bộ máy truy vấn ghép thành phần
    cube: str | None
    measure: str | None
    formula: str | None
    components: tuple[str, ...]
    required_dimensions: tuple[str, ...]
    anomaly: dict[str, Any] | None
    synonyms_vi: tuple[str, ...]
    realizations: tuple[str, ...] = ()
    handbook: dict[str, Any] = field(default_factory=dict)
    per_entity: dict[str, Any] | None = None  # tổng hợp hai bậc: đếm thực thể có `base` ≥ `min`

    @classmethod
    def from_json(cls, d: dict[str, Any], handbook: dict[str, Any] | None = None) -> MetricDef:
        return cls(
            metric=d["metric"],
            name_vi=d["name_vi"],
            description_vi=d.get("description_vi", ""),
            version=d["version"],
            type=d["type"],
            unit=d["unit"],
            good_direction=d.get("good_direction", "none"),
            packs=tuple(d.get("packs", [])),
            hidden=bool(d.get("hidden", False)),
            requires=tuple(d.get("requires", [])),
            dimensions=tuple(d.get("dimensions", [])),
            time_grains=tuple(d.get("time_grains", [])),
            mode=d["mode"],
            cube=d.get("cube"),
            measure=d.get("measure"),
            formula=d.get("formula"),
            components=tuple(d.get("components", [])),
            required_dimensions=tuple(d.get("required_dimensions", [])),
            anomaly=d.get("anomaly"),
            synonyms_vi=tuple(d.get("synonyms_vi", [])),
            realizations=tuple(
                dict.fromkeys([*([d["cube"]] if d.get("cube") else []), *sorted(d.get("realizations") or {})])
            ),
            handbook=handbook or {},
            per_entity=d.get("per_entity"),
        )


class Registry:
    def __init__(self, data: dict[str, Any], handbook: dict[str, Any]) -> None:
        hb = {h["metric"]: h for h in handbook.get("metrics", [])}
        self.library_version: str = data.get("library_version", "")
        self.metrics: dict[str, MetricDef] = {
            name: MetricDef.from_json(d, hb.get(name)) for name, d in data.get("metrics", {}).items()
        }
        self.dimensions: dict[str, dict[str, Any]] = data.get("dimensions", {})
        self.cubes: dict[str, dict[str, Any]] = data.get("cubes", {})
        self.status_cube: str = data.get("status_cube", "mrt_common__data_status")

    def get(self, name: str) -> MetricDef | None:
        return self.metrics.get(name)

    def tenant_eligible(self, m: MetricDef, cfg: TenantConfig) -> bool:
        if cfg.pack not in m.packs:
            return False
        for req in m.requires:
            if req == "identity" and not cfg.features.identity:
                return False
            if req == "amazon" and not cfg.has_amazon():
                return False
        return True

    def visible_for_tenant(self, cfg: TenantConfig) -> list[MetricDef]:
        return [m for m in self.metrics.values() if not m.hidden and self.tenant_eligible(m, cfg)]

    def dimension_column(self, dim: str, cube: str) -> str | None:
        cols = self.dimensions.get(dim, {}).get("columns", {})
        col = cols.get(cube)
        return str(col) if col else None

    def is_internal_dimension(self, dim: str) -> bool:
        return bool(self.dimensions.get(dim, {}).get("internal"))

    def dimension_type(self, dim: str) -> str:
        return str(self.dimensions.get(dim, {}).get("type", "string"))


def _load() -> Registry:
    dist = repo_root() / "semantic" / "dist"
    mp = dist / "metrics.json"
    hp = dist / "handbook.json"
    data = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    hb = json.loads(hp.read_text(encoding="utf-8")) if hp.exists() else {}
    return Registry(data, hb)


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    return _load()


def reload_registry() -> Registry:
    get_registry.cache_clear()
    return get_registry()
