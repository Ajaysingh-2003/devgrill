"""Quick Fire cards from published tracks, and the onboarding calibration's ratings."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import TrackStatus
from devgrill.domain.glicko2 import Rating
from devgrill.infra.models import QuickfireCard, SkillRating, Track


async def deck(
    session: AsyncSession, *, track_slug: str | None, limit: int
) -> Sequence[tuple[QuickfireCard, Track]]:
    """Random cards from published tracks (one track, or all of them)."""
    stmt = (
        select(QuickfireCard, Track)
        .join(Track, Track.id == QuickfireCard.track_id)
        .where(Track.status == TrackStatus.PUBLISHED)
        .order_by(func.random())
        .limit(limit)
    )
    if track_slug:
        stmt = stmt.where(Track.slug == track_slug)
    return (await session.execute(stmt)).tuples().all()


async def calibration_deck(session: AsyncSession) -> list[tuple[QuickfireCard, Track]]:
    """One card per published track, in track order: a random 'core' card where there is one."""
    ranked = (
        select(
            QuickfireCard.id,
            func.row_number()
            .over(
                partition_by=QuickfireCard.track_id,
                # Cards near an even rating first (core cards start at 1500), then at random.
                order_by=(func.abs(QuickfireCard.rating - 1500.0) > 100, func.random()),
            )
            .label("n"),
        )
        .join(Track, Track.id == QuickfireCard.track_id)
        .where(Track.status == TrackStatus.PUBLISHED)
        .subquery()
    )
    rows = await session.execute(
        select(QuickfireCard, Track)
        .join(Track, Track.id == QuickfireCard.track_id)
        .join(ranked, ranked.c.id == QuickfireCard.id)
        .where(ranked.c.n == 1)
        .order_by(Track.position)
    )
    return list(rows.tuples().all())


async def cards_by_id(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[QuickfireCard, Track]]:
    rows = await session.execute(
        select(QuickfireCard, Track)
        .join(Track, Track.id == QuickfireCard.track_id)
        .where(QuickfireCard.id.in_(ids), Track.status == TrackStatus.PUBLISHED)
    )
    return {card.id: (card, track) for card, track in rows.tuples().all()}


async def published_tracks(session: AsyncSession) -> list[Track]:
    rows = await session.scalars(
        select(Track).where(Track.status == TrackStatus.PUBLISHED).order_by(Track.position)
    )
    return list(rows.all())


async def seed_ratings(
    session: AsyncSession, user_id: uuid.UUID, ratings: dict[uuid.UUID, Rating]
) -> list[uuid.UUID]:
    """Insert starting ratings for tracks without one; return the tracks that got one."""
    if not ratings:
        return []
    stmt = (
        insert(SkillRating)
        .values(
            [
                {"user_id": user_id, "track_id": tid, "rating": r.rating, "rd": r.rd, "vol": r.vol}
                for tid, r in ratings.items()
            ]
        )
        .on_conflict_do_nothing(index_elements=["user_id", "track_id"])
        .returning(SkillRating.track_id)
    )
    return list((await session.scalars(stmt)).all())
