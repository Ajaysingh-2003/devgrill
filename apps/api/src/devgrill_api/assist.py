"""AI in the live workspace (ADR 016): teammates who answer, and what happens when they can't.

A war-room message gets a teammate's reply in the background: the POST returns at once and
the reply streams to the workspace over the attempt's SSE stream as `assist` events (typing,
deltas, a reset when a reply is withheld, done). The finished reply is then recorded as a
`reply` event and a war-room message, like a scripted beat.

When AI can't answer (off, over today's budget, over the player's plan allowance, or the
model failing), a `busy` event says so and the scripted war room and the hints carry on.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Coroutine
from datetime import datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select

from devgrill.ai import teammates
from devgrill.ai.port import AiUnavailable, CallMeta, Llm
from devgrill.domain.attempt import TERMINAL_STATES
from devgrill.domain.enums import AuthorKind
from devgrill.domain.streaks import DEFAULT_TIMEZONE, activity_day
from devgrill.infra import assist
from devgrill.infra.events import EventRecorder
from devgrill.infra.models import LlmCall, WarRoomMessage
from devgrill.infra.repositories import attempts as repo
from devgrill.sandbox.lifecycle import events_channel

log = structlog.get_logger(__name__)

BUSY = "Your teammates are busy right now. The hints still work."
OVER_ALLOWANCE = "That's today's teammate replies on your plan. The hints still work."
#: One reply at a time per attempt; a message sent meanwhile is read with the next one.
REPLY_LOCK_S = 60
SHUTDOWN_GRACE_S = 10


def llm_of(state: Any) -> Llm:
    llm: Llm = state.llm
    return llm


def spawn(state: Any, work: Coroutine[Any, Any, None]) -> None:
    """Run AI work after the response; the task is kept so shutdown can wait for it."""
    task = asyncio.create_task(work)
    state.ai_tasks.add(task)
    task.add_done_callback(state.ai_tasks.discard)


async def drain(state: Any, grace_s: float = SHUTDOWN_GRACE_S) -> None:
    tasks = list(getattr(state, "ai_tasks", ()))
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=grace_s)
    for task in pending:
        task.cancel()


async def take_allowance(valkey: Redis, owner_key: str, limit: int, now: datetime) -> bool:
    """Count one AI message (teammate reply or nudge) against today's allowance (IST day)."""
    key = f"ai:messages:{owner_key}:{activity_day(now, DEFAULT_TIMEZONE).isoformat()}"
    used = int(await valkey.incr(key))
    if used == 1:
        await valkey.expire(key, timedelta(days=2))
    return used <= limit


async def publish(valkey: Redis, attempt_id: uuid.UUID, payload: dict[str, Any]) -> None:
    """A live `assist` event on the attempt's SSE stream (not stored, not replayed)."""
    try:
        await valkey.publish(events_channel(str(attempt_id)), json.dumps({"assist": payload}))
    except Exception as exc:
        log.warning("assist.publish_failed", attempt_id=str(attempt_id), error=str(exc)[:200])


async def answer(state: Any, attempt_id: uuid.UUID, user_id: uuid.UUID | None, text: str) -> None:
    """A teammate's reply to the player's latest message, streamed then recorded."""
    valkey: Redis = state.valkey
    factory = state.session_factory
    lock = f"ai:reply:{attempt_id}"
    if not await valkey.set(lock, "1", nx=True, ex=REPLY_LOCK_S):
        return
    reply_id = uuid.uuid4().hex
    try:
        async with factory() as session:
            v = await assist.view(session, attempt_id)
            if v is None or v.attempt.state in TERMINAL_STATES:
                return
            ctx = await assist.persona_context(session, v)
        persona = teammates.choose(text, ctx.conversation, ctx.personas)
        meta = CallMeta("persona", user_id, attempt_id)
        await publish(
            valkey, attempt_id, {"id": reply_id, "kind": "typing", "persona": persona.slug}
        )
        final = ""
        try:
            async for kind, value in teammates.reply(llm_of(state), ctx, persona, meta):
                if kind == "reset":
                    log.warning("assist.reply_withheld", attempt_id=str(attempt_id), why=value)
                    final = ""
                    await publish(valkey, attempt_id, {"id": reply_id, "kind": "reset"})
                else:
                    final += value
                    await publish(
                        valkey, attempt_id, {"id": reply_id, "kind": "delta", "text": value}
                    )
        except AiUnavailable as exc:
            log.info("assist.reply_unavailable", attempt_id=str(attempt_id), reason=exc.reason)
            await publish(valkey, attempt_id, {"id": reply_id, "kind": "busy", "text": BUSY})
            return
        final = final.strip()
        if not final:
            await publish(valkey, attempt_id, {"id": reply_id, "kind": "busy", "text": BUSY})
            return
        async with factory() as session, session.begin():
            metered = await session.scalar(select(LlmCall.id).where(LlmCall.id == meta.call_id))
            await repo.add_event(
                session,
                attempt_id,
                "reply",
                {"id": reply_id, "persona": persona.slug, "text": final},
            )
            session.add(
                WarRoomMessage(
                    attempt_id=attempt_id,
                    author_kind=AuthorKind.PERSONA,
                    persona_key=persona.slug,
                    body=final,
                    llm_call_id=metered,
                )
            )
        await EventRecorder(factory, valkey).announce(attempt_id)
        await publish(valkey, attempt_id, {"id": reply_id, "kind": "done"})
    except Exception:
        log.exception("assist.reply_failed", attempt_id=str(attempt_id))
        await publish(valkey, attempt_id, {"id": reply_id, "kind": "busy", "text": BUSY})
    finally:
        await valkey.delete(lock)


async def busy(state: Any, attempt_id: uuid.UUID, text: str) -> None:
    await publish(state.valkey, attempt_id, {"id": uuid.uuid4().hex, "kind": "busy", "text": text})
