"""Application settings, loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "approval-service"
    app_version: str = "1.0.0"

    # SQLAlchemy async URL. Defaults to a local SQLite file so the app runs
    # with zero infrastructure; docker-compose overrides it with PostgreSQL.
    database_url: str = "sqlite+aiosqlite:///./approval.db"

    log_level: str = "INFO"

    # When true the app creates tables on startup instead of relying on
    # Alembic migrations. Handy for quick local runs and tests; the
    # docker-compose stack keeps it false and runs migrations explicitly.
    auto_create_tables: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
