"""Adapter kho dữ liệu: DuckDB (local) hoặc BigQuery (dev, prod) (spec 00 §4).

Code chỉ chọn adapter theo `DX_ENV`, không rẽ nhánh nghiệp vụ. Mọi dataset có nhãn `tenant_id` (NFR-08).
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from dx_common.config import Settings, get_settings
from dx_common.logging import get_logger

log = get_logger(__name__)


class Warehouse(Protocol):
    kind: str

    def ensure_dataset(self, name: str, labels: dict[str, str], table_expiration_days: int | None = None) -> bool: ...
    def drop_dataset(self, name: str) -> int: ...
    def dataset_exists(self, name: str) -> bool: ...
    def list_tables(self, dataset: str) -> list[str]: ...
    def max_timestamp(self, dataset: str, table: str, column: str) -> datetime | None: ...
    def write_rows(self, dataset: str, table: str, columns: dict[str, str], rows: list[dict[str, Any]]) -> int: ...
    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]: ...
    def execute(self, sql: str) -> None: ...
    def copy_table(self, src: str, dst: str) -> None: ...


_DUCK_TYPES = {
    "string": "VARCHAR",
    "int": "BIGINT",
    "numeric": "DECIMAL(18,4)",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
    "bool": "BOOLEAN",
    "float": "DOUBLE",
}
_BQ_TYPES = {
    "string": "STRING",
    "int": "INT64",
    "numeric": "NUMERIC",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
    "bool": "BOOL",
    "float": "FLOAT64",
}


class DuckDBWarehouse:
    kind = "duckdb"

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self, read_only: bool = False) -> Iterator[Any]:
        import duckdb

        last: Exception | None = None
        for attempt in range(30):
            try:
                con = duckdb.connect(self.path, read_only=read_only)
                break
            except duckdb.IOException as exc:  # file đang bị tiến trình khác giữ khóa ghi
                last = exc
                time.sleep(min(0.2 * (attempt + 1), 2.0))
        else:
            raise RuntimeError(f"Không mở được DuckDB {self.path}: {last}")
        try:
            yield con
        finally:
            con.close()

    def ensure_dataset(self, name: str, labels: dict[str, str], table_expiration_days: int | None = None) -> bool:
        with self.connect() as con:
            existed = bool(
                con.execute(
                    "select count(*) from information_schema.schemata where schema_name = ?", [name]
                ).fetchone()[0]
            )
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{name}"')
        return not existed

    def drop_dataset(self, name: str) -> int:
        with self.connect() as con:
            n = con.execute("select count(*) from information_schema.tables where table_schema = ?", [name]).fetchone()[
                0
            ]
            con.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        return int(n)

    def dataset_exists(self, name: str) -> bool:
        with self.connect(read_only=Path(self.path).exists()) as con:
            return bool(
                con.execute(
                    "select count(*) from information_schema.schemata where schema_name = ?", [name]
                ).fetchone()[0]
            )

    def list_tables(self, dataset: str) -> list[str]:
        if not Path(self.path).exists():
            return []
        with self.connect(read_only=True) as con:
            return [
                r[0]
                for r in con.execute(
                    "select table_name from information_schema.tables where table_schema = ? order by 1", [dataset]
                ).fetchall()
            ]

    def max_timestamp(self, dataset: str, table: str, column: str) -> datetime | None:
        with self.connect(read_only=True) as con:
            row = con.execute(f'select max("{column}") from "{dataset}"."{table}"').fetchone()
        v = row[0] if row else None
        if v is None:
            return None
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v if v.tzinfo else v.replace(tzinfo=UTC)

    def write_rows(self, dataset: str, table: str, columns: dict[str, str], rows: list[dict[str, Any]]) -> int:
        cols = ", ".join(f'"{c}" {_DUCK_TYPES[t]}' for c, t in columns.items())
        with self.connect() as con:
            con.execute(f'CREATE SCHEMA IF NOT EXISTS "{dataset}"')
            con.execute(f'CREATE OR REPLACE TABLE "{dataset}"."{table}" ({cols})')
            if rows:
                ph = ", ".join("?" for _ in columns)
                con.executemany(
                    f'INSERT INTO "{dataset}"."{table}" VALUES ({ph})', [[r.get(c) for c in columns] for r in rows]
                )
        return len(rows)

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        with self.connect(read_only=Path(self.path).exists()) as con:
            return [tuple(r) for r in con.execute(sql, params or []).fetchall()]

    def execute(self, sql: str) -> None:
        with self.connect() as con:
            con.execute(sql)

    def copy_table(self, src: str, dst: str) -> None:
        def q(name: str) -> str:
            schema, table = name.split(".", 1)
            return f'"{schema}"."{table}"'

        with self.connect() as con:
            con.execute(f"CREATE OR REPLACE TABLE {q(dst)} AS SELECT * FROM {q(src)}")


class BigQueryWarehouse:  # pragma: no cover - cần BigQuery thật
    kind = "bigquery"

    def __init__(
        self, project: str, location: str, impersonate: str | None = None, job_labels: dict[str, str] | None = None
    ) -> None:
        from google.cloud import bigquery

        creds = None
        if impersonate:
            import google.auth
            from google.auth import impersonated_credentials

            source, _ = google.auth.default()
            creds = impersonated_credentials.Credentials(
                source_credentials=source,
                target_principal=impersonate,
                target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        self.bq = bigquery
        self.client = bigquery.Client(project=project, location=location, credentials=creds)
        self.project = project
        self.location = location
        self.job_labels = job_labels or {}

    def _job_config(self) -> Any:
        return self.bq.QueryJobConfig(labels=self.job_labels)

    def ensure_dataset(self, name: str, labels: dict[str, str], table_expiration_days: int | None = None) -> bool:
        from google.api_core.exceptions import Conflict

        ds = self.bq.Dataset(f"{self.project}.{name}")
        ds.location = self.location
        ds.labels = labels
        if table_expiration_days:
            ds.default_table_expiration_ms = table_expiration_days * 86400 * 1000
        try:
            self.client.create_dataset(ds)
            return True
        except Conflict:
            existing = self.client.get_dataset(f"{self.project}.{name}")
            if existing.labels != {**existing.labels, **labels}:
                existing.labels = {**existing.labels, **labels}
                self.client.update_dataset(existing, ["labels"])
            return False

    def drop_dataset(self, name: str) -> int:
        tables = self.list_tables(name)
        self.client.delete_dataset(f"{self.project}.{name}", delete_contents=True, not_found_ok=True)
        return len(tables)

    def dataset_exists(self, name: str) -> bool:
        from google.api_core.exceptions import NotFound

        try:
            self.client.get_dataset(f"{self.project}.{name}")
            return True
        except NotFound:
            return False

    def list_tables(self, dataset: str) -> list[str]:
        from google.api_core.exceptions import NotFound

        try:
            return sorted(t.table_id for t in self.client.list_tables(f"{self.project}.{dataset}"))
        except NotFound:
            return []

    def max_timestamp(self, dataset: str, table: str, column: str) -> datetime | None:
        rows = self.query(f"select max(`{column}`) from `{self.project}.{dataset}.{table}`")
        return rows[0][0] if rows else None

    def write_rows(self, dataset: str, table: str, columns: dict[str, str], rows: list[dict[str, Any]]) -> int:
        schema = [self.bq.SchemaField(c, _BQ_TYPES[t]) for c, t in columns.items()]
        cfg = self.bq.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE", labels=self.job_labels)
        clean = [
            {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in r.items() if c in columns} for r in rows
        ]
        self.client.load_table_from_json(clean, f"{self.project}.{dataset}.{table}", job_config=cfg).result()
        return len(rows)

    def query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        cfg = self._job_config()
        if params:
            cfg.query_parameters = [self.bq.ScalarQueryParameter(None, "STRING", str(p)) for p in params]
        return [tuple(r.values()) for r in self.client.query(sql, job_config=cfg).result()]

    def execute(self, sql: str) -> None:
        self.client.query(sql, job_config=self._job_config()).result()

    def copy_table(self, src: str, dst: str) -> None:
        cfg = self.bq.CopyJobConfig(write_disposition="WRITE_TRUNCATE", labels=self.job_labels)
        self.client.copy_table(f"{self.project}.{src}", f"{self.project}.{dst}", job_config=cfg).result()


def tenant_service_account(tenant_id: str, project: str) -> str:
    from dx_common.tenants.naming import service_account_id

    return f"{service_account_id(tenant_id)}@{project}.iam.gserviceaccount.com"


def get_warehouse(tenant_id: str | None = None, settings: Settings | None = None, job: str = "dagster") -> Warehouse:
    s = settings or get_settings()
    if s.is_local:
        return DuckDBWarehouse(s.duckdb_path)
    labels = {"dx_job": job}
    impersonate = None
    if tenant_id:
        labels["tenant_id"] = tenant_id
        if not tenant_id.startswith("hc_"):
            impersonate = tenant_service_account(tenant_id, s.gcp_project_id)
        else:
            impersonate = f"dx-healthcheck@{s.gcp_project_id}.iam.gserviceaccount.com"
    return BigQueryWarehouse(s.gcp_project_id, s.bq_location, impersonate, labels)


def iter_chunks(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    buf: list[Any] = []
    for x in items:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
