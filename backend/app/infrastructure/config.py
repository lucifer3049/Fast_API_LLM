"""Centralised application configuration.

All secrets and tunables are read from environment variables via
pydantic-settings — there is zero hardcoding of credentials. This is the single
source of truth imported across the app (DB URL, JWT secret, LLM keys, seed).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_env: str = "development"
    log_level: str = "INFO"
    # Comma-separated allowed origins for the separated frontend (PLAN Day 6).
    # In dev the Vite server runs on :5173; in compose the SPA is same-origin.
    cors_origins: str = "http://localhost:5173"

    # ---- Database ----
    postgres_user: str = "chat"
    postgres_password: str = "chat"
    postgres_db: str = "chatdb"
    postgres_host: str = "db"
    postgres_port: int = 5432
    # Optional explicit override; if set, takes precedence over the parts above.
    database_url: str | None = None

    # ---- JWT / security ----
    jwt_secret: str = Field(default="dev-insecure-secret-change-me")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_minutes: int = 120

    # ---- Super admin seed (invariant I-1) ----
    super_admin_username: str | None = None
    super_admin_password: str | None = None

    # ---- LLM ----
    llm_provider: str = "mock"  # groq | mock
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_title_model: str = "llama-3.1-8b-instant"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Allowed origins as a list (empty string → no cross-origin allowed)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the env is parsed once per process."""
    return Settings()
