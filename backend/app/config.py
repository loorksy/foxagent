from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FoxAgent"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'foxagent.db'}"
    redis_url: str = ""
    settings_secret: str = ""

    anthropic_api_key: str = ""
    oanda_api_token: str = ""
    oanda_account_id: str = ""
    oanda_environment: str = "practice"
    default_claude_model: str = "claude-sonnet-4-5"

    max_risk_percent: float = 1.0
    min_risk_reward: float = 2.0
    allowed_sessions: str = "london,ny,asian"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def oanda_rest_base(self) -> str:
        if self.oanda_environment.lower() == "live":
            return "https://api-fxtrade.oanda.com"
        return "https://api-fxpractice.oanda.com"

    @property
    def oanda_stream_base(self) -> str:
        if self.oanda_environment.lower() == "live":
            return "https://stream-fxtrade.oanda.com"
        return "https://stream-fxpractice.oanda.com"

    @property
    def oanda_configured(self) -> bool:
        return bool(self.oanda_api_token and self.oanda_account_id)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
