"""Application configuration from environment / .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: str = "dev"
    log_level: str = "INFO"

    telegram_bot_token: SecretStr
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: SecretStr | None = None

    database_url: str = "postgresql+asyncpg://tutorbot:tutorbot@localhost:5432/tutorbot"
    test_database_url: str = "postgresql+asyncpg://tutorbot:tutorbot@localhost:5432/tutorbot_test"

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # set to e.g. https://api.polza.ai/v1 for compatible gateways
    openai_max_tokens: int = 300  # hard cap on LLM response size to control cost

    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_uri: str | None = None

    fernet_key: SecretStr | None = None

    sentry_dsn: str | None = None


    @field_validator("openai_base_url")
    @classmethod
    def _https_only(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith("https://"):
            raise ValueError("openai_base_url must use https://")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
