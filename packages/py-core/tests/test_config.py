from pathlib import Path

import pytest

from devgrill.config import Settings, find_env_file


def test_find_env_file_walks_up(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DEVGRILL_ENV=test\n", encoding="utf-8")
    nested = tmp_path / "apps" / "api"
    nested.mkdir(parents=True)
    assert find_env_file(nested) == tmp_path / ".env"


def test_find_env_file_ignores_folders_without_env(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    found = find_env_file(nested)
    # Nothing inside tmp_path has a .env; anything found must come from above it.
    assert found is None or tmp_path not in found.parents


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVGRILL_ENV", "test")
    monkeypatch.setenv("TEMPORAL_TASK_QUEUE", "q-test")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.env == "test"
    assert settings.temporal_task_queue == "q-test"


def test_settings_defaults_are_local() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "localhost" in settings.database_url
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.otel_enabled is False


def test_cors_origins_split_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:3000, https://devgrill.dev ,")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == ["http://localhost:3000", "https://devgrill.dev"]
