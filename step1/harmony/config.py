from __future__ import annotations

from pathlib import Path
import zoneinfo

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_GATEWAY_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_TIMEZONE = "America/New_York"


class Settings(BaseSettings):
    """App configuration loaded from environment variables."""

    vercel_ai_gateway_api_key: str = Field(
        "",
        alias="VERCEL_AI_GATEWAY_API_KEY",
    )
    vercel_ai_gateway_url: str = Field(
        DEFAULT_GATEWAY_URL,
        alias="VERCEL_AI_GATEWAY_URL",
    )
    timezone: str = Field(
        DEFAULT_TIMEZONE,
        alias="HARMONY_TIMEZONE",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _require_api_key(self):
        if not self.vercel_ai_gateway_api_key.strip():
            raise ValueError(
                "VERCEL_AI_GATEWAY_API_KEY is missing. Put it in the .env file or set the env var."
            )
        return self

    @property
    def tzinfo(self) -> zoneinfo.ZoneInfo:
        """Return a ZoneInfo instance for the configured timezone."""
        return zoneinfo.ZoneInfo(self.timezone)

