"""Cấu hình đọc từ biến môi trường (spec 00 §4.1). Một class `Settings` duy nhất."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["local", "dev", "prod"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    dx_env: Env = "local"
    dx_public_base_url: str = "http://localhost:3000"
    dx_api_public_url: str = "http://localhost:8000"
    dx_team_email: str = ""

    database_url: str = "postgresql+psycopg://dx:dx@localhost:5432/dx"

    gcp_project_id: str = ""
    # FR-OPS-06: bảng billing export của GCP, dạng project.dataset.gcp_billing_export_v1_XXXX
    gcp_billing_export_table: str = ""
    bq_location: str = "asia-southeast1"
    duckdb_path: str = "./.local/dx.duckdb"
    metadata_bucket: str = "./.local/meta"
    hc_bucket: str = "./.local/hc"
    secrets_dir: str = "./.secrets"

    firebase_project_id: str = "dataxland-local"
    firebase_auth_emulator_host: str = ""

    cube_api_url: str = "http://localhost:4000"
    cube_api_secret: str = Field(default="", repr=False)

    internal_api_token: str = Field(default="", repr=False)
    api_internal_url: str = "http://localhost:8000"

    telegram_bot_token: str = Field(default="", repr=False)
    telegram_webhook_secret: str = Field(default="", repr=False)
    telegram_team_chat_id: str = ""
    telegram_bot_username: str = "dataxland_bot"
    telegram_api_base: str = "https://api.telegram.org"
    bot_mode: Literal["webhook", "polling"] = "webhook"
    bot_public_url: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_starttls: bool = True
    email_from: str = "DataxLand <no-reply@dataxland.vn>"

    windsor_api_key: str = Field(default="", repr=False)
    fx_vcb_url: str = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"
    fx_currencies: str = "USD"

    anthropic_api_key: str = Field(default="", repr=False)
    anthropic_model_ask: str = "claude-sonnet-5-5"
    anthropic_model_agent: str = "claude-sonnet-5-5"
    mcp_url: str = "http://localhost:8200/mcp"
    mcp_session_secret: str = Field(default="", repr=False)

    tg_rate_commands: str = "20/600"
    tg_rate_ask_chat: str = "10/3600"
    tg_rate_ask_tenant: str = "50/86400"

    marketplace_oauth_redirect_base: str = "http://localhost:8000"

    @property
    def is_local(self) -> bool:
        return self.dx_env == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Dùng trong test sau khi đổi biến môi trường."""
    get_settings.cache_clear()
