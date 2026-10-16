"""Đẩy siêu dữ liệu chạy lên `METADATA_BUCKET/<tenant_id>/<run_id>/` (spec 04 §3.2, architecture §11.1)."""

from __future__ import annotations

import shutil
from pathlib import Path

from dx_common.config import get_settings

ARTIFACTS = ("manifest.json", "run_results.json", "sources.json", "elementary_report.html")


def upload_run_metadata(tenant_id: str, run_id: str, target_path: Path, bucket: str | None = None) -> list[str]:
    dest = (bucket or get_settings().metadata_bucket).rstrip("/")
    files = [target_path / a for a in ARTIFACTS if (target_path / a).exists()]
    uploaded: list[str] = []
    if dest.startswith("gs://"):  # pragma: no cover - cần GCS
        from google.cloud import storage

        bucket_name, _, prefix = dest[5:].partition("/")
        b = storage.Client().bucket(bucket_name)
        for f in files:
            key = "/".join(x for x in (prefix, tenant_id, run_id, f.name) if x)
            b.blob(key).upload_from_filename(str(f))
            uploaded.append(f"gs://{bucket_name}/{key}")
        return uploaded
    out = Path(dest) / tenant_id / run_id
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, out / f.name)
        uploaded.append(str(out / f.name))
    return uploaded
