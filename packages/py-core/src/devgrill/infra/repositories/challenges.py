"""Daily and weekly challenges: the same scenario for everyone in a window.

Windows follow the India-first calendar (Asia/Kolkata): a daily challenge runs midnight to
midnight IST, a weekly one from Monday 00:00 IST. The scenario is picked deterministically
from the published catalog, so every API instance agrees without coordination. The row is
created on first request (ON CONFLICT DO NOTHING on the window's unique key); a Temporal
schedule takes this over when challenges get leaderboards (phase 9).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import ChallengeKind, ScenarioStatus
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.models import Challenge, ChallengeEntry, Scenario


@dataclass(frozen=True, slots=True)
class Window:
    starts_at: datetime
    ends_at: datetime


def window(kind: ChallengeKind, now: datetime, timezone: str = DEFAULT_TIMEZONE) -> Window:
    local = now.astimezone(ZoneInfo(timezone))
    day = local.date()
    if kind is ChallengeKind.WEEKLY:
        day -= timedelta(days=day.weekday())
    start = datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone))
    length = timedelta(days=7 if kind is ChallengeKind.WEEKLY else 1)
    return Window(start.astimezone(UTC), (start + length).astimezone(UTC))


async def current(
    session: AsyncSession, kind: ChallengeKind, *, now: datetime | None = None
) -> tuple[Challenge, int] | None:
    """The challenge for the window containing `now` (created if missing), and its players."""
    w = window(kind, now or datetime.now(UTC))
    challenge = await _find(session, kind, w)
    if challenge is None:
        candidates = (
            (
                await session.execute(
                    select(Scenario.current_version_id)
                    .where(
                        Scenario.status == ScenarioStatus.PUBLISHED,
                        Scenario.current_version_id.is_not(None),
                    )
                    .order_by(Scenario.slug)
                )
            )
            .scalars()
            .all()
        )
        if not candidates:
            return None
        seed = hashlib.sha256(f"{kind.value}:{w.starts_at.isoformat()}".encode()).digest()
        pick = candidates[int.from_bytes(seed[:8]) % len(candidates)]
        await session.execute(
            insert(Challenge)
            .values(kind=kind, scenario_version_id=pick, starts_at=w.starts_at, ends_at=w.ends_at)
            .on_conflict_do_nothing(index_elements=["kind", "starts_at"])
        )
        challenge = await _find(session, kind, w)
        if challenge is None:
            return None
    players = (
        await session.execute(
            select(func.count())
            .select_from(ChallengeEntry)
            .where(ChallengeEntry.challenge_id == challenge.id)
        )
    ).scalar_one()
    return challenge, int(players)


async def _find(session: AsyncSession, kind: ChallengeKind, w: Window) -> Challenge | None:
    result = await session.execute(
        select(Challenge).where(Challenge.kind == kind, Challenge.starts_at == w.starts_at)
    )
    return result.scalar_one_or_none()
