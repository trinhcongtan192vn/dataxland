"""Đăng ký router (spec 05 §1)."""

from __future__ import annotations

import importlib

from fastapi import FastAPI

ROUTERS = [
    "me",
    "tenants",
    "members",
    "partners",
    "metrics",
    "inputs",
    "reports",
    "decisions",
    "partner",
    "telegram",
    "connect",
    "ops",
    "integrations",
    "health_checks",
    "internal",
    "ask",
    "identity",
    "costs",
    "carriers",
]


def register_routers(app: FastAPI) -> None:
    for name in ROUTERS:
        mod = importlib.import_module(f"app.routers.{name}")
        app.include_router(mod.router)
