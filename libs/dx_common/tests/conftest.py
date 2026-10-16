from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine

from dx_common.events.tables import metadata
from dx_common.testing import ephemeral_postgres


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    with ephemeral_postgres() as url:
        yield url


@pytest.fixture()
def events_engine(pg_url: str) -> Iterator[Engine]:
    eng = create_engine(pg_url)
    metadata.drop_all(eng)
    metadata.create_all(eng)
    yield eng
    eng.dispose()
