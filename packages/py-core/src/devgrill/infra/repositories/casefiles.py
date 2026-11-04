"""Case files (ADR 018): which scenarios can show one, and what a player has answered."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import ScenarioStatus
from devgrill.domain.spec import ScenarioSpec
from devgrill.infra.models import (
    Attempt,
    CaseFilePlay,
    Postmortem,
    PostmortemGrade,
    Scenario,
    ScenarioVersion,
    Track,
)


@dataclass(frozen=True, slots=True)
class CaseRow:
    scenario: Scenario
    track_slug: str
    track_title: str
    spec: ScenarioSpec


def _published() -> Any:
    return (
        select(Scenario, Track.slug, Track.title, ScenarioVersion.spec)
        .join(Track, Track.id == Scenario.track_id)
        .join(ScenarioVersion, ScenarioVersion.id == Scenario.current_version_id)
        .where(
            Scenario.status == ScenarioStatus.PUBLISHED,
            ScenarioVersion.spec["playable"].as_boolean().is_not(False),
        )
    )


def _row(found: Any) -> CaseRow:
    scenario, track_slug, track_title, spec = found
    return CaseRow(scenario, track_slug, track_title, ScenarioSpec.model_validate(spec))


async def published(session: AsyncSession) -> list[CaseRow]:
    rows = await session.execute(_published().order_by(Track.position, Scenario.title))
    return [_row(r) for r in rows]


async def published_one(session: AsyncSession, slug: str) -> CaseRow | None:
    found = (await session.execute(_published().where(Scenario.slug == slug))).one_or_none()
    return _row(found) if found is not None else None


async def scores(session: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(CaseFilePlay.scenario_id, CaseFilePlay.score).where(CaseFilePlay.user_id == user_id)
    )
    return {scenario_id: score for scenario_id, score in rows}


async def play(
    session: AsyncSession, user_id: uuid.UUID, scenario_id: uuid.UUID
) -> CaseFilePlay | None:
    found: CaseFilePlay | None = await session.scalar(
        select(CaseFilePlay).where(
            CaseFilePlay.user_id == user_id, CaseFilePlay.scenario_id == scenario_id
        )
    )
    return found


async def keep_first(
    session: AsyncSession,
    user_id: uuid.UUID,
    scenario_id: uuid.UUID,
    *,
    choices: dict[str, str],
    score: int,
) -> CaseFilePlay:
    """Keep these answers unless the player has already answered: the first ones stand."""
    await session.execute(
        insert(CaseFilePlay)
        .values(user_id=user_id, scenario_id=scenario_id, choices=choices, score=score)
        .on_conflict_do_nothing(constraint="uq_case_file_plays_user_id_scenario_id")
    )
    found = await play(session, user_id, scenario_id)
    assert found is not None
    return found


async def save_review(session: AsyncSession, play_id: uuid.UUID, write_up: str, note: str) -> None:
    found = await session.get(CaseFilePlay, play_id)
    if found is not None:
        found.write_up = write_up
        found.review_note = note
        found.reviewed_at = datetime.now(UTC)


async def reviews_used(session: AsyncSession, user_id: uuid.UUID, since: datetime | None) -> int:
    """Write-up reviews spent since `since`: postmortems and case files share one allowance."""
    graded = (
        select(func.count())
        .select_from(PostmortemGrade)
        .join(Postmortem, Postmortem.id == PostmortemGrade.postmortem_id)
        .join(Attempt, Attempt.id == Postmortem.attempt_id)
        .where(Attempt.user_id == user_id)
    )
    cases = (
        select(func.count())
        .select_from(CaseFilePlay)
        .where(CaseFilePlay.user_id == user_id, CaseFilePlay.reviewed_at.is_not(None))
    )
    if since is not None:
        graded = graded.where(PostmortemGrade.created_at >= since)
        cases = cases.where(CaseFilePlay.reviewed_at >= since)
    return int(await session.scalar(graded) or 0) + int(await session.scalar(cases) or 0)
