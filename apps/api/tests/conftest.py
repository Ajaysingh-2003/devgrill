from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from devgrill.config import Settings
from devgrill_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, log_format="json", readiness_timeout_s=0.5)  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
