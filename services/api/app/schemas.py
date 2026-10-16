"""Model dùng chung cho response."""

from __future__ import annotations

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


class Ok(BaseModel):
    ok: bool = True
