"""Catalog queries: tracks, topics, scenarios and per-user progress over them."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, Text, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import AttemptState, Difficulty, ScenarioStatus, TrackStatus
from devgrill.infra.models import (
    Approach,
    Attempt,
    Scenario,
    ScenarioVersion,
    SkillRating,
    Topic,
    Track,
)

_RESOLVED = AttemptState.RESOLVED


@dataclass(frozen=True, slots=True)
class TrackRow:
    track: Track
    scenario_count: int
    topics: list[Topic]


@dataclass(frozen=True, slots=True)
class ScenarioRow:
    scenario: Scenario
    track_slug: str
    topic: Topic | None
    #: Its current version can be played live (placeholders show a briefing only).
    playable: bool = True


@dataclass(frozen=True, slots=True)
class Progress:
    solved: int
    attempted: int


@dataclass(frozen=True, slots=True)
class Stats:
    players: int
    ended: int
    resolved: int
    median_minutes: float | None


async def published_tracks(session: AsyncSession) -> list[TrackRow]:
    counts = (
        select(Scenario.track_id, func.count().label("n"))
        .where(Scenario.status == ScenarioStatus.PUBLISHED)
        .group_by(Scenario.track_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Track, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.track_id == Track.id)
            .where(Track.status == TrackStatus.PUBLISHED)
            .order_by(Track.position)
        )
    ).all()
    topics = await _topics_by_track(session, [t.id for t, _ in rows])
    return [TrackRow(track=t, scenario_count=int(n), topics=topics.get(t.id, [])) for t, n in rows]


async def _topics_by_track(
    session: AsyncSession, track_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Topic]]:
    if not track_ids:
        return {}
    result = await session.execute(
        select(Topic).where(Topic.track_id.in_(track_ids)).order_by(Topic.position)
    )
    grouped: dict[uuid.UUID, list[Topic]] = {}
    for topic in result.scalars():
        grouped.setdefault(topic.track_id, []).append(topic)
    return grouped


async def track_by_slug(session: AsyncSession, slug: str) -> TrackRow | None:
    track = (
        await session.execute(
            select(Track).where(Track.slug == slug, Track.status == TrackStatus.PUBLISHED)
        )
    ).scalar_one_or_none()
    if track is None:
        return None
    count = (
        await session.execute(
            select(func.count())
            .select_from(Scenario)
            .where(Scenario.track_id == track.id, Scenario.status == ScenarioStatus.PUBLISHED)
        )
    ).scalar_one()
    topics = await _topics_by_track(session, [track.id])
    return TrackRow(track=track, scenario_count=int(count), topics=topics.get(track.id, []))


def scenarios_query(
    *,
    track_slug: str | None = None,
    topic_slug: str | None = None,
    difficulty: Difficulty | None = None,
    query: str | None = None,
    after_slug: str | None = None,
    limit: int = 20,
    order_by_difficulty: bool = False,
) -> Select[Scenario, str, Topic, bool | None]:
    """Published scenarios, keyset-paginated on slug (or all of a track by difficulty).

    Exposed separately so the query-plan test can EXPLAIN exactly what the API runs.
    """
    # Whether the current version is playable (placeholders aren't): joined, not a subquery
    # per row, so a whole track still lists in one pass.
    stmt = (
        select(Scenario, Track.slug, Topic, ScenarioVersion.spec["playable"].as_boolean())
        .join(Track, Track.id == Scenario.track_id)
        .outerjoin(Topic, Topic.id == Scenario.topic_id)
        .outerjoin(ScenarioVersion, ScenarioVersion.id == Scenario.current_version_id)
        .where(Scenario.status == ScenarioStatus.PUBLISHED, Track.status == TrackStatus.PUBLISHED)
    )
    if track_slug:
        stmt = stmt.where(Track.slug == track_slug)
    if topic_slug:
        stmt = stmt.where(Topic.slug == topic_slug)
    if difficulty:
        stmt = stmt.where(Scenario.difficulty == difficulty)
    if query:
        # Treat the user's text literally: escape LIKE's wildcards and the escape character.
        escaped = query.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(Scenario.title.ilike(pattern) | Scenario.summary.ilike(pattern))
    if order_by_difficulty:
        return stmt.order_by(Scenario.difficulty, Scenario.title)
    if after_slug:
        stmt = stmt.where(Scenario.slug > after_slug)
    return stmt.order_by(Scenario.slug).limit(limit)


async def scenarios(session: AsyncSession, **filters: Any) -> list[ScenarioRow]:
    rows = (await session.execute(scenarios_query(**filters))).all()
    return [
        ScenarioRow(scenario=s, track_slug=t, topic=topic, playable=playable is not False)
        for s, t, topic, playable in rows
    ]


async def scenario_by_slug(
    session: AsyncSession, slug: str, *, published_only: bool = True
) -> tuple[ScenarioRow, Track, ScenarioVersion] | None:
    stmt = (
        select(Scenario, Track, Topic, ScenarioVersion)
        .join(Track, Track.id == Scenario.track_id)
        .outerjoin(Topic, Topic.id == Scenario.topic_id)
        .join(ScenarioVersion, ScenarioVersion.id == Scenario.current_version_id)
        .where(Scenario.slug == slug)
    )
    if published_only:
        stmt = stmt.where(
            Scenario.status == ScenarioStatus.PUBLISHED, Track.status == TrackStatus.PUBLISHED
        )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    scenario, track, topic, version = row
    return ScenarioRow(scenario=scenario, track_slug=track.slug, topic=topic), track, version


async def scenario_row(session: AsyncSession, scenario_id: uuid.UUID) -> ScenarioRow | None:
    """A published scenario by id, with its track slug and topic."""
    row = (
        await session.execute(
            select(Scenario, Track.slug, Topic)
            .join(Track, Track.id == Scenario.track_id)
            .outerjoin(Topic, Topic.id == Scenario.topic_id)
            .where(Scenario.id == scenario_id, Scenario.status == ScenarioStatus.PUBLISHED)
        )
    ).first()
    if row is None:
        return None
    scenario, track_slug, topic = row
    return ScenarioRow(scenario=scenario, track_slug=track_slug, topic=topic)


def _attempted_scenarios(user_id: uuid.UUID) -> Select[uuid.UUID, bool]:
    """Per scenario the user has touched: whether any attempt resolved it."""
    return (
        select(
            ScenarioVersion.scenario_id,
            func.bool_or(Attempt.state == _RESOLVED).label("solved"),
        )
        .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
        .where(Attempt.user_id == user_id)
        .group_by(ScenarioVersion.scenario_id)
    )


async def scenario_progress(
    session: AsyncSession, user_id: uuid.UUID, scenario_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not scenario_ids:
        return {}
    stmt = _attempted_scenarios(user_id).where(ScenarioVersion.scenario_id.in_(scenario_ids))
    return {
        sid: "solved" if solved else "attempted" for sid, solved in (await session.execute(stmt))
    }


async def track_progress(session: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, Progress]:
    touched = _attempted_scenarios(user_id).subquery()
    stmt = (
        select(
            Scenario.track_id,
            func.count().filter(touched.c.solved.is_(True)),
            func.count().filter(touched.c.solved.is_(False)),
        )
        .join(touched, touched.c.scenario_id == Scenario.id)
        .where(Scenario.status == ScenarioStatus.PUBLISHED)
        .group_by(Scenario.track_id)
    )
    return {
        track_id: Progress(solved=int(s), attempted=int(a))
        for track_id, s, a in await session.execute(stmt)
    }


async def topic_progress(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Track, Topic | None, int, int]]:
    """(track, topic, solved, total) for every published scenario grouping."""
    touched = _attempted_scenarios(user_id).subquery()
    stmt = (
        select(
            Track,
            Topic,
            func.count().filter(touched.c.solved.is_(True)),
            func.count(Scenario.id),
        )
        .select_from(Scenario)
        .join(Track, Track.id == Scenario.track_id)
        .outerjoin(Topic, Topic.id == Scenario.topic_id)
        .outerjoin(touched, touched.c.scenario_id == Scenario.id)
        .where(Scenario.status == ScenarioStatus.PUBLISHED, Track.status == TrackStatus.PUBLISHED)
        .group_by(Track.id, Topic.id)
        .order_by(Track.position, Topic.position)
    )
    return [(t, topic, int(s), int(n)) for t, topic, s, n in await session.execute(stmt)]


async def ratings(session: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, SkillRating]:
    result = await session.execute(select(SkillRating).where(SkillRating.user_id == user_id))
    return {r.track_id: r for r in result.scalars()}


async def stats(session: AsyncSession, scenario_id: uuid.UUID) -> Stats:
    ended = Attempt.ended_at.is_not(None)
    minutes = func.extract("epoch", Attempt.resolved_at - Attempt.started_at) / 60
    row = (
        await session.execute(
            select(
                # A player is a user, or a guest before they sign up.
                func.count(
                    func.distinct(
                        func.coalesce(Attempt.user_id.cast(Text), Attempt.guest_token_hash)
                    )
                ),
                func.count().filter(ended),
                func.count().filter(Attempt.state == _RESOLVED),
                func.percentile_cont(0.5).within_group(minutes).filter(Attempt.state == _RESOLVED),
            )
            .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
            .where(ScenarioVersion.scenario_id == scenario_id)
        )
    ).one()
    players, ended_count, resolved, median = row
    return Stats(
        players=int(players),
        ended=int(ended_count),
        resolved=int(resolved),
        median_minutes=float(median) if median is not None else None,
    )


async def warmup(session: AsyncSession, scenario: Scenario) -> ScenarioRow | None:
    """The hardest published scenario in the same track that is still easier than this one."""
    order = [Difficulty.SEV4, Difficulty.SEV3, Difficulty.SEV2, Difficulty.SEV1]
    easier = order[: order.index(scenario.difficulty)]
    if not easier:
        return None
    stmt = (
        select(Scenario, Track.slug, Topic)
        .join(Track, Track.id == Scenario.track_id)
        .outerjoin(Topic, Topic.id == Scenario.topic_id)
        .where(
            Scenario.track_id == scenario.track_id,
            Scenario.status == ScenarioStatus.PUBLISHED,
            Scenario.difficulty.in_(easier),
            Scenario.id != scenario.id,
        )
        # Prefer the same topic, then the closest difficulty.
        .order_by(
            case((Scenario.topic_id == scenario.topic_id, 0), else_=1),
            Scenario.difficulty.desc(),
            Scenario.slug,
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    s, track_slug, topic = row
    return ScenarioRow(scenario=s, track_slug=track_slug, topic=topic)


async def has_resolved(session: AsyncSession, user_id: uuid.UUID, scenario_id: uuid.UUID) -> bool:
    stmt = (
        select(func.count())
        .select_from(Attempt)
        .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
        .where(
            and_(
                Attempt.user_id == user_id,
                ScenarioVersion.scenario_id == scenario_id,
                Attempt.state == _RESOLVED,
            )
        )
    )
    return bool((await session.execute(stmt)).scalar_one())


async def approaches(session: AsyncSession, scenario_id: uuid.UUID) -> list[Approach]:
    result = await session.execute(
        select(Approach).where(Approach.scenario_id == scenario_id).order_by(Approach.key)
    )
    return list(result.scalars())
