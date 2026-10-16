"""HTTP client dùng chung cho connector sàn (spec 01 §2.1).

- Retry với backoff lũy thừa có jitter, tối đa 5 lần; lỗi 429 dùng thời gian chờ nền tảng trả về (`Retry-After`).
- Lỗi xác thực ném `AuthExpired` để connector làm mới token rồi thử lại một lần.
- Không log body phản hồi; chỉ log đường dẫn, mã lỗi, số lần thử.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from connectors.base import SourceError
from dx_common.logging import get_logger

log = get_logger(__name__)

MAX_RETRIES = 5


class AuthExpired(Exception):
    """Token hết hạn hoặc không hợp lệ ở nguồn."""


class RateLimited(Exception):
    def __init__(self, wait_s: float | None = None) -> None:
        super().__init__("rate limited")
        self.wait_s = wait_s


class TransientError(Exception):
    """Lỗi tạm thời ở nguồn (5xx, lỗi hệ thống của nền tảng): thử lại."""


def backoff_seconds(
    attempt: int, base: float = 1.0, cap: float = 60.0, rng: Callable[[], float] = random.random
) -> float:
    """Full jitter: ngẫu nhiên trong [0, min(cap, base × 2^attempt)]."""
    return rng() * min(cap, base * (2**attempt))


class HttpClient:
    """Bọc `httpx.Client`. Lớp con định nghĩa `check(resp, body)` để phân loại lỗi theo nền tảng."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self.rng = rng
        self.http = httpx.Client(timeout=timeout_s, transport=transport)

    def close(self) -> None:
        self.http.close()

    def check(self, resp: httpx.Response, body: Any) -> None:
        """Mặc định: 401/403 → AuthExpired; 429 → RateLimited; 5xx → TransientError."""
        if resp.status_code in (401, 403):
            raise AuthExpired()
        if resp.status_code == 429:
            raise RateLimited(_retry_after(resp))
        if resp.status_code >= 500:
            raise TransientError(str(resp.status_code))
        if resp.status_code >= 400:
            raise SourceError("api_error", f"HTTP {resp.status_code}")

    def send(self, method: str, url: str, **kw: Any) -> Any:
        """Gửi một request đã ký sẵn (`url` tuyệt đối hoặc đường dẫn). Trả body JSON đã qua `check`."""
        full = url if url.startswith("http") else f"{self.base_url}{url}"
        path = httpx.URL(full).path
        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.http.request(method, full, **kw)
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                self.check(resp, body)
                return body
            except RateLimited as exc:
                last = exc
                wait = exc.wait_s if exc.wait_s is not None else backoff_seconds(attempt, rng=self.rng)
                log.warning("nguồn giới hạn tần suất", extra={"path": path, "attempt": attempt, "wait_s": wait})
            except (TransientError, httpx.TransportError) as exc:
                last = exc
                wait = backoff_seconds(attempt, rng=self.rng)
                log.warning(
                    "lỗi tạm thời ở nguồn", extra={"path": path, "attempt": attempt, "error": type(exc).__name__}
                )
            if attempt < MAX_RETRIES:
                self.sleep(wait)
        if isinstance(last, RateLimited):
            raise SourceError("rate_limited", f"{path}: vượt giới hạn tần suất sau {MAX_RETRIES} lần thử")
        raise SourceError("api_error", f"{path}: lỗi sau {MAX_RETRIES} lần thử ({type(last).__name__})")


def _retry_after(resp: httpx.Response) -> float | None:
    v = resp.headers.get("Retry-After")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None
