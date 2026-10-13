"""Property-based contract tests: every /v1 operation, fuzzed from the OpenAPI schema.

Schemathesis generates requests (valid and invalid) for each operation and checks that the
API never 500s, only returns documented status codes and content types, and that every
response body matches its schema. Runs against a live uvicorn server on the test database.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import schemathesis
import uvicorn
from conftest import valkey_url_for_tests
from schemathesis.openapi import from_url

from devgrill.config import Settings
from devgrill_api.auth.jwks import JwksCache
from devgrill_api.main import create_app
from devgrill_api.testing import make_signer

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"
USER = uuid.uuid4()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_api(migrated_database: str) -> Iterator[tuple[str, str]]:
    """(base_url, user_token): the API on a real port, plus a token it trusts."""
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from devgrill.infra import db
    from devgrill_content.seed import seed

    async def prepare() -> None:
        engine = create_async_engine(migrated_database)
        async with db.create_session_factory(engine)() as session, session.begin():
            await seed(session, CONTENT)
        await engine.dispose()

    asyncio.run(prepare())

    signer = make_signer()  # module-scoped, so not the per-test `signer` fixture
    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        log_format="json",
        log_level="WARNING",
        database_url=migrated_database,
        valkey_url=valkey_url_for_tests(),
        auth_issuer="http://localhost:3000",
        auth_audience="devgrill-api",
        internal_hmac_secret="c" * 40,
        guest_token_secret="c" * 40,
        rate_limit_default=100_000,
    )
    app = create_app(settings)
    app.state.jwks = JwksCache(signer.fetch, min_refresh_s=0)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("API did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", signer.token(USER, login="schemathesis", exp_in=3600)
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def api_schema(live_api: tuple[str, str]) -> schemathesis.BaseSchema:
    base_url, token = live_api
    schema = from_url(f"{base_url}/openapi.json")
    schema.config.update(base_url=base_url, headers={"Authorization": f"Bearer {token}"})
    schema.config.generation.update(max_examples=25)
    # A schema can't describe "a cursor we issued earlier": well-formed but unknown cursors
    # are rejected with 400 invalid_cursor, which is correct behaviour, not a contract break.
    schema.config.checks.positive_data_acceptance.expected_statuses = [
        "2xx",
        "3xx",
        "400",
        "401",
        "403",
        "404",
        "409",
        "429",
    ]
    return schema


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.include(path_regex=r"^/v1/").parametrize()
def test_v1_conforms_to_its_contract(case: schemathesis.Case) -> None:
    case.call_and_validate()
