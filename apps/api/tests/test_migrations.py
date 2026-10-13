"""Schema guarantees, checked against a real Postgres (docs/PLAN.md §9.3, phase 2 gate)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from conftest import _recreate_database, database_url_for_tests, run_alembic
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from devgrill.domain.attempt import LIVE_STATES
from devgrill.domain.enums import AttemptMode, AttemptState
from devgrill.infra.models import Attempt, Profile

pytestmark = pytest.mark.integration


def test_upgrade_downgrade_upgrade_on_an_empty_database() -> None:
    url = database_url_for_tests().replace("devgrill_test", "devgrill_roundtrip_test")
    asyncio.run(_recreate_database(url))
    for step in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        result = run_alembic(url, *step)
        assert result.returncode == 0, f"{step}: {result.stderr}"


def test_models_and_migrations_agree(migrated_database: str) -> None:
    # `alembic check` fails if autogenerate would produce any operation.
    result = run_alembic(migrated_database, "check")
    assert result.returncode == 0, result.stdout + result.stderr


async def test_every_foreign_key_has_an_index(db_engine: AsyncEngine) -> None:
    query = text(
        """
        SELECT c.conrelid::regclass::text, c.conname
        FROM pg_constraint c
        WHERE c.contype = 'f' AND c.connamespace = 'app'::regnamespace
          AND NOT EXISTS (
            SELECT 1 FROM pg_index i
            WHERE i.indrelid = c.conrelid
              AND (i.indkey::int2[])[0:array_length(c.conkey, 1) - 1] @> c.conkey
              AND (i.indkey::int2[])[0:array_length(c.conkey, 1) - 1] <@ c.conkey
          )
        """
    )
    async with db_engine.connect() as conn:
        unindexed = (await conn.execute(query)).all()
    assert unindexed == []


async def test_circular_foreign_keys_exist(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        names = set(
            (
                await conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint WHERE connamespace = 'app'::regnamespace"
                        " AND contype = 'f'"
                    )
                )
            ).scalars()
        )
    assert "fk_scenarios_current_version_id_scenario_versions" in names
    assert "fk_approaches_discovered_from_attempt_id_attempts" in names


async def _seed_version(session: AsyncSession) -> uuid.UUID:
    track = (
        await session.execute(
            text(
                "INSERT INTO app.tracks (slug, title, summary, icon, position)"
                " VALUES ('t', 'T', 's', 'db', 0) RETURNING id"
            )
        )
    ).scalar_one()
    scenario = (
        await session.execute(
            text(
                "INSERT INTO app.scenarios"
                " (slug, track_id, title, summary, difficulty, est_minutes)"
                " VALUES ('s', :t, 'S', 's', 'sev3', 10) RETURNING id"
            ),
            {"t": track},
        )
    ).scalar_one()
    return (
        await session.execute(
            text(
                "INSERT INTO app.scenario_versions (scenario_id, version, content_hash)"
                " VALUES (:s, 1, 'h') RETURNING id"
            ),
            {"s": scenario},
        )
    ).scalar_one()


async def test_one_live_attempt_per_user_is_enforced_by_the_database(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    db_session.add(Profile(user_id=user_id, handle="ana", display_name="Ana"))
    version = await _seed_version(db_session)
    await db_session.flush()

    live = sorted(LIVE_STATES)
    db_session.add(
        Attempt(
            user_id=user_id, scenario_version_id=version, mode=AttemptMode.GUIDED, state=live[0]
        )
    )
    # Ended attempts don't count against the limit.
    db_session.add(
        Attempt(
            user_id=user_id,
            scenario_version_id=version,
            mode=AttemptMode.GUIDED,
            state=AttemptState.RESOLVED,
        )
    )
    await db_session.flush()

    db_session.add(
        Attempt(
            user_id=user_id, scenario_version_id=version, mode=AttemptMode.GUIDED, state=live[1]
        )
    )
    with pytest.raises(IntegrityError, match="uq_attempts_user_id_live"):
        await db_session.flush()


async def test_attempts_need_an_owner(db_session: AsyncSession) -> None:
    version = await _seed_version(db_session)
    db_session.add(Attempt(scenario_version_id=version, mode=AttemptMode.GUIDED))
    with pytest.raises(IntegrityError, match="ck_attempts_owner_present"):
        await db_session.flush()


async def test_handles_are_case_insensitive_and_validated(db_session: AsyncSession) -> None:
    db_session.add(Profile(user_id=uuid.uuid4(), handle="Ana", display_name="Ana"))
    await db_session.flush()
    db_session.add(Profile(user_id=uuid.uuid4(), handle="ana", display_name="Other"))
    with pytest.raises(IntegrityError, match="uq_profiles_handle"):
        await db_session.flush()
    await db_session.rollback()
    db_session.add(Profile(user_id=uuid.uuid4(), handle="-bad", display_name="Bad"))
    with pytest.raises(IntegrityError, match="ck_profiles_handle_format"):
        await db_session.flush()
