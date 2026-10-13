"""Alembic environment (async). Owns only the `app` schema; Better Auth owns `auth`."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import devgrill.infra.models  # noqa: F401  (registers every table on Base.metadata)
from devgrill.config import get_settings
from devgrill.infra.db import APP_SCHEMA, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    # Never autogenerate changes for tables outside our schema (e.g. Better Auth's `auth`).
    if type_ == "table":
        return obj.schema == APP_SCHEMA
    return True


def _configure(connection: Connection | None = None) -> None:
    common = {
        "target_metadata": target_metadata,
        "include_schemas": True,
        "include_object": include_object,
        "compare_type": True,
    }
    if connection is None:
        context.configure(
            url=config.get_main_option("sqlalchemy.url"),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **common,
        )
    else:
        context.configure(connection=connection, **common)


def run_migrations_offline() -> None:
    _configure()
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
