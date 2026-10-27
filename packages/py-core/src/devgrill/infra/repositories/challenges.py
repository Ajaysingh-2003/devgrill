"""Daily and weekly challenges: the same scenario for everyone in a window.

Windows follow the India-first calendar (Asia/Kolkata): a daily challenge runs midnight to
midnight IST, a weekly one from Monday 00:00 IST. The scenario is picked deterministically
from the rotation (published, playable, in the Daily rotation), so every API instance agrees
without coordination. The worker's ChallengeRollover schedule creates each window's row at
midnight IST; the first request still creates it if the schedule hasn't (ON CONFLICT DO
NOTHING on the window's unique key).
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import ChallengeKind, ScenarioStatus
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.models import Challenge, ChallengeEntry, Scenario, ScenarioVersion


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
        candidates = await rotation(session)
        if not candidates:
            return None
        pick = pick_for(kind, w, candidates)
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


async def rotation(session: AsyncSession) -> list[uuid.UUID]:
    """Current versions of the scenarios a challenge may use, in a stable order."""
    spec = ScenarioVersion.spec
    rows = await session.execute(
        select(Scenario.current_version_id)
        .join(ScenarioVersion, ScenarioVersion.id == Scenario.current_version_id)
        .where(
            Scenario.status == ScenarioStatus.PUBLISHED,
            # Missing keys mean the defaults (playable, in the rotation).
            spec["playable"].as_boolean().is_not(False),
            spec["daily"].as_boolean().is_not(False),
        )
        .order_by(Scenario.slug)
    )
    return [v for v in rows.scalars().all() if v is not None]


def pick_for(kind: ChallengeKind, w: Window, candidates: list[uuid.UUID]) -> uuid.UUID:
    """The same pick on every instance for the same window.

    The rotation is played in shuffled cycles: every scenario once per cycle, a fresh order
    each cycle, and a cycle never opens with the scenario that closed the previous one, so two
    windows in a row never repeat (with two or more scenarios).
    """
    n = len(candidates)
    number = w.starts_at.date().toordinal() // (7 if kind is ChallengeKind.WEEKLY else 1)
    if n <= 2:
        return candidates[number % n]

    def shuffled(cycle: int) -> list[int]:
        order = list(range(n))
        random.Random(f"{kind.value}:{cycle}").shuffle(order)  # noqa: S311 - not security
        return order

    cycle, position = divmod(number, n)
    order = shuffled(cycle)
    if order[0] == shuffled(cycle - 1)[-1]:  # swapping 0 and 1 never moves the last (n > 2)
        order[0], order[1] = order[1], order[0]
    return candidates[order[position]]


async def ensure(session: AsyncSession, now: datetime) -> list[str]:
    """Create the daily and weekly challenges for the windows containing `now` (idempotent)."""
    made = []
    for kind in (ChallengeKind.DAILY, ChallengeKind.WEEKLY):
        if await current(session, kind, now=now) is not None:
            made.append(kind.value)
    return made


async def _find(session: AsyncSession, kind: ChallengeKind, w: Window) -> Challenge | None:
    result = await session.execute(
        select(Challenge).where(Challenge.kind == kind, Challenge.starts_at == w.starts_at)
    )
    return result.scalar_one_or_none()
