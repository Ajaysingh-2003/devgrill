"""Settings shared by every Python service, read from the environment and the repo-root .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BRAND_NAME = "DevGrill"


def find_env_file(start: Path | None = None) -> Path | None:
    """Return the nearest .env walking up from `start` (default: cwd).

    Services are started from the repo root by `just`, but tests and IDE runs may start
    from a sub-folder, so we look upwards instead of assuming a working directory.
    """
    current = (start or Path.cwd()).resolve()
    for folder in (current, *current.parents):
        candidate = folder / ".env"
        if candidate.is_file():
            return candidate
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    env: Literal["dev", "test", "prod"] = Field(default="dev", alias="DEVGRILL_ENV")
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    database_url: str = "postgresql+asyncpg://devgrill:devgrill@localhost:5432/devgrill"
    valkey_url: str = "redis://localhost:6379/0"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "devgrill-default"

    # Comma-separated: plain strings survive every .env loader (just, docker, shells) unchanged.
    api_cors_origins: str = "http://localhost:3000"
    readiness_timeout_s: float = 2.0

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    sentry_dsn: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
