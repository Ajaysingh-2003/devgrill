"""A user's ratings, streak, activity and attempt history."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.attempt import LIVE_STATES
from devgrill.domain.enums import AttemptState, Difficulty, StreakMode
from devgrill.domain.streaks import compute_streak
from devgrill.infra.models import (
    ActivityDay,
    Attempt,
    LeaveDay,
    RatingHistory,
    Scenario,
    ScenarioVersion,
    SkillRating,
    Streak,
    Track,
)


@dataclass(frozen=True, slots=True)
class AttemptRow:
    attempt: Attempt
    scenario_slug: str
    scenario_title: str
    difficulty: Difficulty
    track_slug: str


async def ratings_with_history(
    session: AsyncSession, user_id: uuid.UUID, *, history_limit: int = 30
) -> list[tuple[Track, SkillRating, list[tuple[datetime, float]]]]:
    rows = (
        await session.execute(
            select(Track, SkillRating)
            .join(SkillRating, SkillRating.track_id == Track.id)
            # Calibration's starting points (no games yet) aren't shown as ratings.
            .where(SkillRating.user_id == user_id, SkillRating.games > 0)
            .order_by(Track.position)
        )
    ).all()
    out: list[tuple[Track, SkillRating, list[tuple[datetime, float]]]] = []
    for track, rating in rows:
        ranked = (
            select(
                RatingHistory.ts,
                RatingHistory.after["rating"].as_float().label("rating"),
            )
            .where(RatingHistory.user_id == user_id, RatingHistory.track_id == track.id)
            .order_by(RatingHistory.ts.desc())
            .limit(history_limit)
            .subquery()
        )
        points = (await session.execute(select(ranked).order_by(ranked.c.ts))).all()
        out.append((track, rating, [(ts, float(r)) for ts, r in points]))
    return out


async def activity_days(session: AsyncSession, user_id: uuid.UUID, since: date) -> list[date]:
    result = await session.execute(
        select(ActivityDay.day)
        .where(ActivityDay.user_id == user_id, ActivityDay.day >= since)
        .order_by(ActivityDay.day)
    )
    return list(result.scalars())


async def refresh_streak(
    session: AsyncSession, user_id: uuid.UUID, *, today: date, mode: StreakMode
) -> Streak:
    """Recompute the derived streak row from activity_days (it is never incremented)."""
    days = list(
        (
            await session.execute(select(ActivityDay.day).where(ActivityDay.user_id == user_id))
        ).scalars()
    )
    streak = await session.get(Streak, user_id)
    if streak is None:
        streak = Streak(user_id=user_id, mode=mode, freezes=0)
        session.add(streak)
        await session.flush()
    leave = list(
        (await session.execute(select(LeaveDay.day).where(LeaveDay.user_id == user_id))).scalars()
    )
    # Freezes are derived too: earned by play, spent on misses (devgrill.domain.streaks).
    summary = compute_streak(days, today, mode=mode, leave=leave)
    await session.execute(
        update(Streak)
        .where(Streak.user_id == user_id)
        .values(
            mode=mode,
            current=summary.current,
            longest=max(summary.longest, streak.longest),
            freezes=summary.freezes,
            last_day=summary.last_day,
        )
    )
    await session.refresh(streak)
    return streak


async def attempts(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    before: tuple[datetime, uuid.UUID] | None = None,
    limit: int = 20,
) -> list[AttemptRow]:
    """Newest first, keyset-paginated on (started_at, id)."""
    stmt = (
        select(Attempt, Scenario.slug, Scenario.title, Scenario.difficulty, Track.slug)
        .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
        .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
        .join(Track, Track.id == Scenario.track_id)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.started_at.desc(), Attempt.id.desc())
        .limit(limit)
    )
    if before is not None:
        started, attempt_id = before
        stmt = stmt.where(
            (Attempt.started_at < started)
            | ((Attempt.started_at == started) & (Attempt.id < attempt_id))
        )
    return [
        AttemptRow(
            attempt=a, scenario_slug=slug, scenario_title=title, difficulty=diff, track_slug=track
        )
        for a, slug, title, diff, track in await session.execute(stmt)
    ]


async def resolved_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Attempt)
        .where(Attempt.user_id == user_id, Attempt.state == AttemptState.RESOLVED)
    )
    return int(result.scalar_one())


async def claim_guest_attempts(session: AsyncSession, user_id: uuid.UUID, guest_hash: str) -> int:
    """Attach a guest's attempts to the account that just signed up. Idempotent.

    Ended attempts are always claimed. A live attempt is claimed only if the user has none
    (one live attempt per user, enforced by a unique index); at most the newest one moves,
    and anything left unclaimed simply expires.
    """
    claimed = await session.execute(
        update(Attempt)
        .where(
            Attempt.guest_token_hash == guest_hash,
            Attempt.user_id.is_(None),
            Attempt.state.not_in(LIVE_STATES),
        )
        .values(user_id=user_id)
        .returning(Attempt.id)
    )
    count = len(claimed.all())

    user_has_live = (
        await session.execute(
            select(func.count())
            .select_from(Attempt)
            .where(Attempt.user_id == user_id, Attempt.state.in_(LIVE_STATES))
        )
    ).scalar_one() > 0
    if not user_has_live:
        newest_live = (
            select(Attempt.id)
            .where(
                Attempt.guest_token_hash == guest_hash,
                Attempt.user_id.is_(None),
                Attempt.state.in_(LIVE_STATES),
            )
            .order_by(Attempt.started_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        moved = await session.execute(
            update(Attempt)
            .where(Attempt.id == newest_live)
            .values(user_id=user_id)
            .returning(Attempt.id)
        )
        count += len(moved.all())
    return count


async def record_activity(session: AsyncSession, user_id: uuid.UUID, day: date, kind: str) -> None:
    """Mark `day` active for `kind` (idempotent). Any Quick Fire answer counts (PLAN §8.5)."""
    stmt = insert(ActivityDay).values(user_id=user_id, day=day, kinds=[kind])
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id", "day"],
            set_={
                "kinds": case(
                    (ActivityDay.kinds.contains([kind]), ActivityDay.kinds),
                    else_=func.array_append(ActivityDay.kinds, kind),
                )
            },
        )
    )


async def leave_days(session: AsyncSession, user_id: uuid.UUID, since: date) -> list[date]:
    result = await session.execute(
        select(LeaveDay.day)
        .where(LeaveDay.user_id == user_id, LeaveDay.day >= since)
        .order_by(LeaveDay.day)
    )
    return list(result.scalars())


async def replace_upcoming_leave(
    session: AsyncSession, user_id: uuid.UUID, today: date, days: list[date]
) -> None:
    """Set the leave from `today` on to exactly `days` (past leave stays as it was)."""
    await session.execute(
        delete(LeaveDay).where(LeaveDay.user_id == user_id, LeaveDay.day >= today)
    )
    if days:
        await session.execute(
            insert(LeaveDay)
            .values([{"user_id": user_id, "day": d} for d in sorted(set(days))])
            .on_conflict_do_nothing()
        )
