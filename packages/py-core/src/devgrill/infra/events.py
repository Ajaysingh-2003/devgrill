"""Record attempt events, fire the scenario's beats, and wake SSE listeners.

The worker (state changes, boot steps, timed beats), the gateway (CLI and UI actions) and the
API (hints, messages, mitigation claims) all record through `EventRecorder`, so every in-world
event lands in `attempt_events`, triggers its `when:` beats exactly once, and is announced on
Valkey for the SSE stream (domain rules: `devgrill.domain.events`).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devgrill.domain.enums import AuthorKind
from devgrill.domain.events import beats_for_trigger
from devgrill.domain.spec import Beat, ScenarioSpec
from devgrill.infra.models import Attempt, AttemptEvent, ScenarioVersion, WarRoomMessage
from devgrill.infra.repositories import attempts
from devgrill.sandbox.lifecycle import events_channel

log = structlog.get_logger(__name__)


async def scenario_spec(session: AsyncSession, attempt_id: uuid.UUID) -> ScenarioSpec | None:
    spec = await session.scalar(
        select(ScenarioVersion.spec)
        .join(Attempt, Attempt.scenario_version_id == ScenarioVersion.id)
        .where(Attempt.id == attempt_id)
    )
    return ScenarioSpec.model_validate(spec) if spec is not None else None


async def fired_beats(session: AsyncSession, attempt_id: uuid.UUID) -> set[int]:
    rows = await session.scalars(
        select(AttemptEvent.payload).where(
            AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == "beat"
        )
    )
    return {int(p["index"]) for p in rows if isinstance(p, dict) and "index" in p}


async def add_beat(session: AsyncSession, attempt_id: uuid.UUID, index: int, beat: Beat) -> None:
    await attempts.add_event(
        session, attempt_id, "beat", {"index": index, "persona": beat.persona, "say": beat.say}
    )
    session.add(
        WarRoomMessage(
            attempt_id=attempt_id,
            author_kind=AuthorKind.PERSONA,
            persona_key=beat.persona,
            body=beat.say,
        )
    )


async def fire_trigger(session: AsyncSession, attempt_id: uuid.UUID, trigger: str) -> int:
    """Add the beats `trigger` fires (each beat fires once per attempt). Returns how many."""
    spec = await scenario_spec(session, attempt_id)
    if spec is None or not spec.beats:
        return 0
    due = beats_for_trigger(spec.beats, trigger, await fired_beats(session, attempt_id))
    for index, beat in due:
        await add_beat(session, attempt_id, index, beat)
    return len(due)


class EventRecorder:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], valkey: Redis | None
    ) -> None:
        self.session_factory = session_factory
        self.valkey = valkey

    async def announce(self, attempt_id: uuid.UUID | str) -> None:
        if self.valkey is None:
            return
        try:
            await self.valkey.publish(events_channel(str(attempt_id)), "1")
        except Exception as exc:
            log.warning("events.publish_failed", attempt_id=str(attempt_id), error=str(exc))

    async def record(
        self,
        attempt_id: uuid.UUID,
        type_: str,
        payload: dict[str, Any],
        *,
        trigger: str | None = None,
    ) -> None:
        async with self.session_factory() as session, session.begin():
            await attempts.add_event(session, attempt_id, type_, payload)
            if type_ == "message":
                session.add(
                    WarRoomMessage(
                        attempt_id=attempt_id,
                        author_kind=AuthorKind.USER,
                        body=str(payload.get("text", "")),
                    )
                )
            if trigger:
                await fire_trigger(session, attempt_id, trigger)
        await self.announce(attempt_id)

    async def beat(self, attempt_id: uuid.UUID, index: int) -> bool:
        """Fire beat `index` (a timed beat) unless it already fired. True if it was added."""
        async with self.session_factory() as session, session.begin():
            spec = await scenario_spec(session, attempt_id)
            if spec is None or index >= len(spec.beats):
                return False
            if index in await fired_beats(session, attempt_id):
                return False
            await add_beat(session, attempt_id, index, spec.beats[index])
        await self.announce(attempt_id)
        return True
