"""Shared fixtures for integration tests that need Postgres and Valkey (`just deps-up`).

Tests never touch the dev database: they create `devgrill_test` from scratch, migrate it with
Alembic once per session, and truncate the app tables before each test that asks for them.
Valkey uses database 15, flushed per test.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ROOT = Path(__file__).parent
TEST_DATABASE = "devgrill_test"
TEST_VALKEY_DB = 15


def _base_url() -> str:
    from devgrill.config import Settings

    return Settings().database_url


def database_url_for_tests() -> str:
    return make_url(_base_url()).set(database=TEST_DATABASE).render_as_string(hide_password=False)


def valkey_url_for_tests() -> str:
    from devgrill.config import Settings

    base = Settings().valkey_url.rsplit("/", 1)[0]
    return f"{base}/{TEST_VALKEY_DB}"


async def _recreate_database(url: str) -> None:
    parsed = make_url(url)
    # Safety: this drops the database, so it must be a throwaway test one.
    assert parsed.database, "no database name"
    assert parsed.database.endswith("_test"), f"refusing to drop {parsed.database!r}"
    conn = await asyncpg.connect(
        user=parsed.username,
        password=parsed.password,
        host=parsed.host,
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{parsed.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{parsed.database}"')
    finally:
        await conn.close()


def run_alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run Alembic against `url` in a subprocess (env.py reads DATABASE_URL at import)."""
    env = {**os.environ, "DATABASE_URL": url, "PYTHONUTF8": "1"}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "apps/api/alembic.ini"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """A freshly created and fully migrated test database. Returns its URL."""
    url = database_url_for_tests()
    asyncio.run(_recreate_database(url))
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    return url


APP_TABLES_SQL = """
SELECT string_agg(format('%I.%I', schemaname, tablename), ', ')
FROM pg_tables WHERE schemaname = 'app' AND tablename <> 'alembic_version'
"""


@pytest.fixture
async def db_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database)
    async with engine.begin() as conn:
        tables = (await conn.execute(text(APP_TABLES_SQL))).scalar_one()
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def repo_root() -> Path:
    return ROOT
