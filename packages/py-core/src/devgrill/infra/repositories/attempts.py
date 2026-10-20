"""Attempts, their sandbox sessions and their event log (the investigation trail).

The workflow's activities and the API both go through here, so state moves always pass the
domain lifecycle (`devgrill.domain.attempt`) and every move leaves an `attempt_events` row.
Usage counting for the entitlement policy (ADR 013) lives here too.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.attempt import LIVE_STATES, transition
from devgrill.domain.enums import AttemptMode, AttemptState, SandboxDriver
from devgrill.infra.models import Attempt, AttemptEvent, SandboxSession

#: Tiers whose minutes count against the global free budget.
BUDGETED_TIERS = ("guest", "free")


class AttemptLiveError(Exception):
    """The owner already has a live attempt (the partial unique index said so)."""


@dataclass(frozen=True, slots=True)
class Owner:
    user_id: uuid.UUID | None = None
    guest_hash: str | None = None

    def __post_init__(self) -> None:
        if (self.user_id is None) == (self.guest_hash is None):
            raise ValueError("an owner is a user or a guest, not both")

    def where(self) -> Any:
        if self.user_id is not None:
            return Attempt.user_id == self.user_id
        return and_(Attempt.guest_token_hash == self.guest_hash, Attempt.user_id.is_(None))


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------- attempts


async def get(session: AsyncSession, attempt_id: uuid.UUID) -> Attempt | None:
    return await session.get(Attempt, attempt_id)


async def live_for(session: AsyncSession, owner: Owner) -> Attempt | None:
    return await session.scalar(
        select(Attempt).where(owner.where(), Attempt.state.in_(LIVE_STATES)).limit(1)
    )


async def create(
    session: AsyncSession, *, owner: Owner, scenario_version_id: uuid.UUID, mode: AttemptMode
) -> Attempt:
    """Insert a provisioning attempt. Raises AttemptLiveError if one is already live."""
    attempt = Attempt(
        user_id=owner.user_id,
        guest_token_hash=owner.guest_hash if owner.user_id is None else None,
        scenario_version_id=scenario_version_id,
        mode=mode,
        state=AttemptState.PROVISIONING,
    )
    session.add(attempt)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        if "uq_attempts_user_id_live" in str(exc.orig):
            raise AttemptLiveError from exc
        raise
    await add_event(session, attempt.id, "state", {"to": AttemptState.PROVISIONING.value})
    return attempt


_STAMPS = {
    AttemptState.ACTIVE: "active_at",
    AttemptState.MITIGATED: "mitigated_at",
    AttemptState.RESOLVED: "resolved_at",
}


async def move(
    session: AsyncSession, attempt_id: uuid.UUID, target: AttemptState, **payload: Any
) -> Attempt:
    """Move an attempt to `target` (lifecycle-checked), stamp the time, log the event.

    Moving to the state it is already in is a no-op, so retried activities are safe.
    """
    attempt = await session.get(Attempt, attempt_id, with_for_update=True)
    if attempt is None:
        raise LookupError(f"attempt {attempt_id} not found")
    if attempt.state is target:
        return attempt
    attempt.state = transition(attempt.state, target)
    now = _now()
    stamp = _STAMPS.get(target)
    if stamp and getattr(attempt, stamp) is None:
        setattr(attempt, stamp, now)
    if target not in LIVE_STATES and attempt.ended_at is None:
        attempt.ended_at = now
    await add_event(session, attempt_id, "state", {"to": target.value, **payload})
    return attempt


async def add_event(
    session: AsyncSession, attempt_id: uuid.UUID, type_: str, payload: dict[str, Any]
) -> AttemptEvent:
    event = AttemptEvent(attempt_id=attempt_id, type=type_, payload=payload)
    session.add(event)
    await session.flush()
    return event


async def events_after(
    session: AsyncSession, attempt_id: uuid.UUID, after_id: int, limit: int = 200
) -> list[AttemptEvent]:
    rows = await session.scalars(
        select(AttemptEvent)
        .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.id > after_id)
        .order_by(AttemptEvent.id)
        .limit(limit)
    )
    return list(rows)


# ---------------------------------------------------------------------------- sessions


async def open_session(
    session: AsyncSession,
    *,
    attempt_id: uuid.UUID,
    driver: SandboxDriver,
    external_ref: str,
    resources: dict[str, Any],
    expires_at: datetime,
) -> SandboxSession:
    """The sandbox for an attempt. Reuses the open one (a retried provision), else creates it."""
    existing = await session.scalar(
        select(SandboxSession).where(
            SandboxSession.attempt_id == attempt_id, SandboxSession.destroyed_at.is_(None)
        )
    )
    if existing is not None:
        existing.external_ref, existing.expires_at, existing.state = (
            external_ref,
            expires_at,
            "provisioning",
        )
        return existing
    row = SandboxSession(
        attempt_id=attempt_id,
        driver=driver,
        host="local",
        external_ref=external_ref,
        state="provisioning",
        resources=resources,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return row


async def mark_ready(session: AsyncSession, attempt_id: uuid.UUID, expires_at: datetime) -> None:
    row = await _open(session, attempt_id)
    if row is not None:
        row.state = "ready"
        row.ready_at = row.ready_at or _now()
        row.expires_at = expires_at


async def set_expiry(session: AsyncSession, attempt_id: uuid.UUID, expires_at: datetime) -> None:
    row = await _open(session, attempt_id)
    if row is not None:
        row.expires_at = expires_at


async def close_session(
    session: AsyncSession,
    attempt_id: uuid.UUID,
    *,
    cpu_seconds: float | None,
    cost_per_hour_usd: float,
) -> SandboxSession | None:
    row = await _open(session, attempt_id)
    if row is None:
        return None
    now = _now()
    row.state = "destroyed"
    row.destroyed_at = now
    row.cpu_seconds = cpu_seconds
    hours = (now - row.created_at).total_seconds() / 3600
    row.est_cost_usd = Decimal(str(round(hours * cost_per_hour_usd, 4)))
    return row


async def _open(session: AsyncSession, attempt_id: uuid.UUID) -> SandboxSession | None:
    return await session.scalar(
        select(SandboxSession)
        .where(SandboxSession.attempt_id == attempt_id, SandboxSession.destroyed_at.is_(None))
        .order_by(SandboxSession.created_at.desc())
        .limit(1)
    )


# ------------------------------------------------------------------------------ usage


def _minutes(since: datetime | None, now: datetime) -> Any:
    """Sandbox minutes from ready to destroyed (or now), clipped to the period."""
    start = (
        SandboxSession.ready_at if since is None else func.greatest(SandboxSession.ready_at, since)
    )
    end = func.coalesce(SandboxSession.destroyed_at, literal(now))
    return func.coalesce(func.sum(func.greatest(func.date_part("epoch", end - start), 0)), 0) / 60.0


async def owner_usage(
    session: AsyncSession,
    owner: Owner,
    *,
    starts_since: datetime | None,
    minutes_since: datetime | None,
) -> tuple[int, int, float]:
    """(live attempts, starts in the starts period, sandbox minutes in the minutes period)."""
    now = _now()
    live = await session.scalar(
        select(func.count())
        .select_from(Attempt)
        .where(owner.where(), Attempt.state.in_(LIVE_STATES))
    )
    started = select(func.count()).select_from(Attempt).where(owner.where())
    if starts_since is not None:
        started = started.where(Attempt.started_at >= starts_since)
    minutes = (
        select(_minutes(minutes_since, now))
        .select_from(SandboxSession)
        .join(Attempt, Attempt.id == SandboxSession.attempt_id)
        .where(owner.where(), SandboxSession.ready_at.is_not(None))
    )
    if minutes_since is not None:
        minutes = minutes.where(
            or_(SandboxSession.destroyed_at.is_(None), SandboxSession.destroyed_at > minutes_since)
        )
    return (
        int(live or 0),
        int(await session.scalar(started) or 0),
        float(await session.scalar(minutes) or 0),
    )


async def fleet_usage(session: AsyncSession, *, day_start: datetime) -> tuple[int, float]:
    """(live sandboxes across everyone, minutes used today by budgeted tiers)."""
    now = _now()
    live = await session.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.state.in_(LIVE_STATES))
    )
    budgeted = await session.scalar(
        select(_minutes(day_start, now))
        .select_from(SandboxSession)
        .where(
            SandboxSession.ready_at.is_not(None),
            SandboxSession.resources["tier"].astext.in_(BUDGETED_TIERS),
            or_(SandboxSession.destroyed_at.is_(None), SandboxSession.destroyed_at > day_start),
        )
    )
    return int(live or 0), float(budgeted or 0)
