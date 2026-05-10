"""Application configuration from environment / .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
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
    openai_model: str = "gpt-4o"

    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_uri: str | None = None

    fernet_key: SecretStr | None = None

    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
