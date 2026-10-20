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

    # ---- auth (ADR 005, ADR 011)
    auth_jwks_url: str = "http://localhost:3000/api/auth/jwks"
    auth_issuer: str = "http://localhost:3000"
    auth_audience: str = "devgrill-api"
    #: How long a fetched JWKS is trusted before a background refresh.
    auth_jwks_ttl_s: float = 600.0
    #: An unknown `kid` triggers a refetch at most this often (rotation without hammering).
    auth_jwks_min_refresh_s: float = 30.0
    internal_hmac_secret: str = ""
    guest_token_secret: str = ""
    guest_token_ttl_days: int = 30
    admin_github_logins: str = ""

    # ---- rate limits (requests per window, per user or per IP)
    rate_limit_default: int = 300
    rate_limit_window_s: int = 60
    rate_limit_enabled: bool = True

    # ---- sandboxes (ADR 007, ADR 013)
    sandbox_driver: Literal["compose"] = "compose"
    #: Folder holding tracks.yaml, scenarios/, faults/ and base-apps/ (relative to the repo root).
    content_root: Path = Path("content")
    #: Docker Engine endpoint; empty uses the platform default (npipe on Windows).
    docker_host: str = ""
    #: Fleet cap: sandboxes alive at once across all users.
    sandbox_max_live: int = 4
    #: Total sandbox-minutes free and guest users may use per IST day (the money cap).
    sandbox_daily_minutes_budget: int = 600
    #: Kill switch for free and guest starts.
    sandbox_free_starts: bool = True
    #: Scenarios guests may play on /try (comma-separated slugs).
    sandbox_guest_scenarios: str = "ttl-zero"
    sandbox_provision_timeout_s: int = 180
    #: Rough marginal cost of one sandbox-hour, for `est_cost_usd` (ADR 013: about $0.01).
    sandbox_cost_per_hour_usd: float = 0.012
    #: The probe image (platform-owned; runs scrapes, load and verifier checks).
    sandbox_probe_image: str = "devgrill/sandbox-probe:1"

    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    sentry_dsn: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def guest_scenarios(self) -> frozenset[str]:
        return frozenset(s.strip() for s in self.sandbox_guest_scenarios.split(",") if s.strip())

    @property
    def admin_logins(self) -> frozenset[str]:
        return frozenset(
            login.strip().lower() for login in self.admin_github_logins.split(",") if login.strip()
        )

    def require_secrets(self) -> None:
        """Refuse to start outside dev/test with missing signing secrets."""
        if self.env == "prod":
            missing = [
                name
                for name in ("internal_hmac_secret", "guest_token_secret")
                if len(getattr(self, name)) < 32
            ]
            if missing:
                raise RuntimeError(f"missing or weak secrets: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
