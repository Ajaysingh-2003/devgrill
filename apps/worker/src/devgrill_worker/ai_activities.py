"""AI work after the incident (ADR 016): the debrief's coach note and approach, and the
postmortem review. The logic lives in `devgrill.infra.assist`; these are its activities."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from devgrill.ai.port import AiUnavailable, Llm
from devgrill.infra import assist
from devgrill.infra.events import EventRecorder
from devgrill.infra.repositories import attempts

log = structlog.get_logger(__name__)

#: What the player reads when a review can't be done (the reason stays in the logs).
REVIEW_FAILED = "The review couldn't be finished. Try again later."


@dataclass(frozen=True, slots=True)
class ReviewFailedInput:
    attempt_id: str
    detail: str = REVIEW_FAILED


class AiActivities:
    def __init__(
        self,
        *,
        llm: Llm,
        judge_model: str,
        session_factory: async_sessionmaker[AsyncSession],
        valkey: Redis | None,
    ) -> None:
        self.llm = llm
        self.judge_model = judge_model
        self.session_factory = session_factory
        self.recorder = EventRecorder(session_factory, valkey)

    @activity.defn(name="attempt.review")
    async def review(self, attempt_id: str) -> None:
        """Coach note and approach for a settled attempt (best effort, idempotent)."""
        added = await assist.review_attempt(self.session_factory, self.llm, uuid.UUID(attempt_id))
        log.info("ai.attempt_reviewed", attempt_id=attempt_id, added=sorted(added or {}))

    @activity.defn(name="postmortem.grade")
    async def grade(self, attempt_id: str) -> bool:
        """Grade the submitted postmortem. False when AI can't (recorded for the player);
        other errors raise, for Temporal to retry."""
        try:
            await assist.grade_postmortem(
                self.session_factory,
                self.llm,
                uuid.UUID(attempt_id),
                judge_model=self.judge_model,
            )
        except AiUnavailable as exc:
            log.warning("ai.review_unavailable", attempt_id=attempt_id, reason=exc.reason)
            await self.failed(ReviewFailedInput(attempt_id))
            return False
        return True

    @activity.defn(name="postmortem.review_failed")
    async def failed(self, inp: ReviewFailedInput) -> None:
        async with self.session_factory() as session, session.begin():
            await attempts.add_event(
                session,
                uuid.UUID(inp.attempt_id),
                "review",
                {"status": "failed", "detail": inp.detail},
            )

    def all(self) -> list[Callable[..., Any]]:
        return [self.review, self.grade, self.failed]
