"""Fixture cho test dbt (spec 02 §8, §9)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from dbt_helpers import REPO, Built, dbt_run, seed


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Built]:
    tmp = tmp_path_factory.mktemp("dbt")
    path = tmp / "dx.duckdb"
    seed(path)
    for t in ("demo_seller", "demo_agency"):
        res = dbt_run(path, t)
        assert not res.runtime_error, res.stdout_tail[-3000:]
    yield Built(path, tmp)


@pytest.fixture()
def scratch_samples(tmp_path: Path) -> Path:
    dst = tmp_path / "samples"
    shutil.copytree(REPO / "transform" / "samples", dst, ignore=shutil.ignore_patterns("files"))
    return dst
