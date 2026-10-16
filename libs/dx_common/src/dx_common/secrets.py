"""Đọc và ghi bí mật (spec 00 §1.1, spec 01 §2.2).

- `local`: file trong `SECRETS_DIR` (mặc định `./.secrets/`), mỗi secret một file, phiên bản mới ghi đè.
- `dev`, `prod`: Google Secret Manager của `GCP_PROJECT_ID`.

Không bao giờ log giá trị secret.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from dx_common.config import Settings, get_settings

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


class SecretNotFound(KeyError):
    pass


class SecretStore(Protocol):
    def get(self, name: str) -> str: ...
    def put(self, name: str, value: str) -> None: ...
    def exists(self, name: str) -> bool: ...


def _check_name(name: str) -> str:
    # secret_ref có thể ở dạng đầy đủ projects/<p>/secrets/<name>
    short = name.rsplit("/", 1)[-1]
    if not _NAME_RE.match(short):
        raise ValueError("Tên secret không hợp lệ")
    return short


class LocalFileSecretStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / _check_name(name)

    def get(self, name: str) -> str:
        p = self._path(name)
        if not p.exists():
            raise SecretNotFound(_check_name(name))
        return p.read_text(encoding="utf-8")

    def put(self, name: str, value: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(name).write_text(value, encoding="utf-8")

    def exists(self, name: str) -> bool:
        return self._path(name).exists()


class GcpSecretStore:  # pragma: no cover - cần GCP thật
    def __init__(self, project: str) -> None:
        from google.cloud import secretmanager

        self.project = project
        self.client = secretmanager.SecretManagerServiceClient()

    def _secret_path(self, name: str) -> str:
        return f"projects/{self.project}/secrets/{_check_name(name)}"

    def get(self, name: str) -> str:
        from google.api_core.exceptions import NotFound

        try:
            resp = self.client.access_secret_version(name=self._secret_path(name) + "/versions/latest")
        except NotFound as exc:
            raise SecretNotFound(_check_name(name)) from exc
        return str(resp.payload.data.decode("utf-8"))

    def put(self, name: str, value: str) -> None:
        from google.api_core.exceptions import AlreadyExists

        try:
            self.client.create_secret(
                parent=f"projects/{self.project}",
                secret_id=_check_name(name),
                secret={"replication": {"automatic": {}}, "labels": {"dx": "true"}},
            )
        except AlreadyExists:
            pass
        self.client.add_secret_version(parent=self._secret_path(name), payload={"data": value.encode("utf-8")})

    def exists(self, name: str) -> bool:
        from google.api_core.exceptions import NotFound

        try:
            self.client.get_secret(name=self._secret_path(name))
        except NotFound:
            return False
        return True


_store: SecretStore | None = None


def get_secret_store(settings: Settings | None = None) -> SecretStore:
    global _store
    if _store is not None:
        return _store
    s = settings or get_settings()
    _store = LocalFileSecretStore(s.secrets_dir) if s.is_local else GcpSecretStore(s.gcp_project_id)
    return _store


def set_secret_store(store: SecretStore | None) -> None:
    """Cho test thay kho secret."""
    global _store
    _store = store


def get_json(name: str) -> dict[str, Any]:
    data = json.loads(get_secret_store().get(name))
    if not isinstance(data, dict):
        raise ValueError("Secret không phải JSON object")
    return data


def put_json(name: str, value: dict[str, Any]) -> None:
    get_secret_store().put(name, json.dumps(value, ensure_ascii=False, sort_keys=True))
