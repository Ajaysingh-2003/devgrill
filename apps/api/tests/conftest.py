from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from conftest import valkey_url_for_tests
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.config import Settings
from devgrill_api.auth.jwks import JwksCache
from devgrill_api.main import create_app
from devgrill_api.testing import (
    AUDIENCE,
    CONTENT,
    ISSUER,
    FakeGateway,
    FakeOrchestrator,
    Signer,
    make_signer,
)
from devgrill_content.seed import seed

TEST_SECRET = "test-secret-" + "x" * 40


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, log_format="json", readiness_timeout_s=0.5)  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def signer() -> Signer:
    return make_signer()


@pytest.fixture
def api_settings(migrated_database: str) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        log_format="json",
        database_url=migrated_database,
        valkey_url=valkey_url_for_tests(),
        auth_issuer=ISSUER,
        auth_audience=AUDIENCE,
        internal_hmac_secret=TEST_SECRET,
        guest_token_secret=TEST_SECRET,
        admin_github_logins="root-admin",
        rate_limit_default=1000,
    )


@pytest.fixture
def api(api_settings: Settings, signer: Signer, db_engine: object) -> Iterator[TestClient]:
    """The real app on the test database, trusting `signer` as its JWKS."""
    app = create_app(api_settings)
    app.state.jwks = JwksCache(signer.fetch, ttl_s=600, min_refresh_s=0)
    with TestClient(app) as test_client:
        assert test_client.portal is not None
        test_client.portal.call(app.state.valkey.flushdb)
        yield test_client


AuthHeaders = Callable[..., dict[str, str]]


@pytest.fixture
def auth(signer: Signer) -> AuthHeaders:
    """`auth(user_id, login=..., ...)` -> Authorization headers for a freshly signed token."""

    def headers(sub: str | uuid.UUID | None = None, **claims: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {signer.token(sub, **claims)}"}

    return headers


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed(db_session, CONTENT)
    await db_session.commit()
    return db_session


@pytest.fixture
def fakes(api: TestClient) -> tuple[FakeOrchestrator, FakeGateway]:
    orchestrator, gateway = FakeOrchestrator(), FakeGateway()
    api.app.state.orchestrator = orchestrator  # type: ignore[attr-defined]
    api.app.state.gateway = gateway  # type: ignore[attr-defined]
    api.app.state.settings.content_root = CONTENT  # type: ignore[attr-defined]
    return orchestrator, gateway
