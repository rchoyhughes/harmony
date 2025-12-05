from __future__ import annotations

from pathlib import Path
import zoneinfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_GATEWAY_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_TIMEZONE = "America/New_York"


class Settings(BaseSettings):
    """App configuration loaded from environment variables."""

    vercel_ai_gateway_api_key: str = Field(..., alias="VERCEL_AI_GATEWAY_API_KEY")
    vercel_ai_gateway_url: str = Field(
        DEFAULT_GATEWAY_URL, alias="VERCEL_AI_GATEWAY_URL"
    )
    timezone: str = Field(DEFAULT_TIMEZONE, alias="HARMONY_TIMEZONE")

    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def tzinfo(self) -> zoneinfo.ZoneInfo:
        """Return a ZoneInfo instance for the configured timezone."""
        return zoneinfo.ZoneInfo(self.timezone)

