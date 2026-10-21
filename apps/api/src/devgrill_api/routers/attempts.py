"""Attempts: start a live incident, follow it, steer it (ADR 013 limits apply on start).

Signed-in users and guests (X-Guest-Token, tutorial only) can both play. Every endpoint
checks that the caller owns the attempt; another player's attempt is a 404, not a 403.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Header, Request, Response
from sqlalchemy import select, text
from sse_starlette import EventSourceResponse, ServerSentEvent

from devgrill.domain import entitlements as policy
from devgrill.domain.attempt import TERMINAL_STATES
from devgrill.domain.enums import Access, AttemptState, ChallengeKind, Plan
from devgrill.domain.events import visible
from devgrill.domain.spec import ScenarioSpec
from devgrill.infra.models import Attempt, Entitlement, SandboxSession, Scenario, ScenarioVersion
from devgrill.infra.repositories import attempts as repo
from devgrill.infra.repositories import catalog, challenges
from devgrill.sandbox.lifecycle import (
    SIGNAL_ABANDON,
    SIGNAL_EXTEND,
    SIGNAL_RESET,
    SIGNAL_TOUCH,
    SIGNAL_VERIFY,
    LifecycleInput,
    events_channel,
)
from devgrill_api.auth import guest
from devgrill_api.deps import GuestJti, OptionalUser, SessionDep, SettingsDep
from devgrill_api.errors import AppError
from devgrill_api.orchestrator import Orchestrator, OrchestratorError, TemporalOrchestrator
from devgrill_api.schemas import AttemptIn, AttemptOut, Quota, UsageOut

log = structlog.get_logger(__name__)
router = APIRouter(tags=["attempts"])

#: Serialises start decisions, so two concurrent starts can't both take the last slot.
_START_LOCK = 0x5A4E_D60C
_SSE_PING_S = 15
#: After an attempt ends, how long the stream waits for the teardown's final event.
_SSE_TEARDOWN_GRACE_S = 120


def _orchestrator(request: Request) -> Orchestrator:
    state = request.app.state
    if getattr(state, "orchestrator", None) is None:
        state.orchestrator = TemporalOrchestrator(state.settings)
    orchestrator: Orchestrator = state.orchestrator
    return orchestrator


def _owner(user: OptionalUser, jti: str | None) -> repo.Owner:
    if user is not None:
        return repo.Owner(user_id=user.id)
    if jti is not None:
        return repo.Owner(guest_hash=guest.guest_hash(jti))
    raise AppError(401, "unauthenticated", "Sign in, or start a guest session on /try.")


async def _tier_and_limits(
    session: Any, owner: repo.Owner
) -> tuple[policy.Tier, policy.PlanLimits]:
    if owner.user_id is None:
        return "guest", policy.limits_for("guest")
    row = await session.get(Entitlement, owner.user_id)
    now = datetime.now(UTC)
    plan = (
        row.plan
        if row is not None and (row.valid_until is None or row.valid_until > now)
        else Plan.FREE
    )
    tier: policy.Tier = plan.value  # type: ignore[assignment]
    return tier, policy.limits_for(tier, row.limits if row is not None else None)


async def _usage(
    session: Any, owner: repo.Owner, limits: policy.PlanLimits, now: datetime
) -> policy.Usage:
    live, starts, minutes = await repo.owner_usage(
        session,
        owner,
        starts_since=policy.period_start(now, limits.live_starts_period),
        minutes_since=policy.period_start(now, limits.sandbox_minutes_period),
    )
    return policy.Usage(live_now=live, starts_in_period=starts, minutes_in_period=minutes)


async def _fleet(session: Any, settings: Any, now: datetime) -> policy.Fleet:
    day_start = policy.period_start(now, "day")
    assert day_start is not None
    live_total, budgeted = await repo.fleet_usage(session, day_start=day_start)
    return policy.Fleet(
        live_total=live_total,
        max_live=settings.sandbox_max_live,
        budgeted_minutes_today=budgeted,
        daily_budget_minutes=settings.sandbox_daily_minutes_budget,
        free_starts_enabled=settings.sandbox_free_starts,
    )


async def _attempt_out(session: Any, attempt: Attempt) -> AttemptOut:
    slug = await session.scalar(
        select(Scenario.slug)
        .join(ScenarioVersion, ScenarioVersion.scenario_id == Scenario.id)
        .where(ScenarioVersion.id == attempt.scenario_version_id)
    )
    expires = await session.scalar(
        select(SandboxSession.expires_at)
        .where(SandboxSession.attempt_id == attempt.id)
        .order_by(SandboxSession.created_at.desc())
        .limit(1)
    )
    return AttemptOut(
        id=attempt.id,
        scenario_slug=slug or "",
        mode=attempt.mode,
        state=attempt.state,
        started_at=attempt.started_at,
        active_at=attempt.active_at,
        ended_at=attempt.ended_at,
        expires_at=expires if attempt.state not in TERMINAL_STATES else None,
    )


async def _owned(session: Any, attempt_id: uuid.UUID, owner: repo.Owner) -> Attempt:
    attempt = await repo.get(session, attempt_id)
    mine = attempt is not None and (
        (owner.user_id is not None and attempt.user_id == owner.user_id)
        or (
            owner.user_id is None
            and attempt.user_id is None
            and attempt.guest_token_hash == owner.guest_hash
        )
    )
    if not mine:
        raise AppError(404, "not_found", "No such attempt.")
    assert attempt is not None
    return attempt


@router.post("/attempts", status_code=202, response_model=AttemptOut)
async def start_attempt(
    body: AttemptIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    user: OptionalUser,
    jti: GuestJti,
) -> AttemptOut:
    """Start a live incident: checks the plan, then boots a sandbox (202; follow /events)."""
    owner = _owner(user, jti)
    found = await catalog.scenario_by_slug(session, body.scenario_slug)
    if found is None:
        raise AppError(404, "not_found", "No such scenario.")
    row, _, version = found
    spec = ScenarioSpec.model_validate(version.spec)
    if not spec.playable:
        raise AppError(409, "not_playable", "This incident can't be played live yet.")

    # One decision at a time: the fleet and budget counts must not race.
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _START_LOCK})
    now = datetime.now(UTC)
    tier, limits = await _tier_and_limits(session, owner)
    daily = await challenges.current(session, ChallengeKind.DAILY, now=now)
    decision = policy.decide(
        policy.StartRequest(
            tier=tier,
            limits=limits,
            scenario_access=Access(row.scenario.access),
            is_daily=tier != "guest"
            and daily is not None
            and daily[0].scenario_version_id == version.id,
            is_tutorial=row.scenario.slug in settings.guest_scenarios,
            scenario_ttl_minutes=spec.ttl_minutes,
            usage=await _usage(session, owner, limits, now),
            fleet=await _fleet(session, settings, now),
            now=now,
        )
    )
    if not decision.allowed:
        headers = {"Retry-After": str(decision.retry_after_s)} if decision.retry_after_s else None
        instance = None
        if decision.refusal == "active_attempt_exists":
            live = await repo.live_for(session, owner)
            if live is not None:
                instance = f"/v1/attempts/{live.id}"  # the incident to go back to
        log.info("attempt.refused", refusal=decision.refusal, tier=tier, scenario=row.scenario.slug)
        raise AppError(
            decision.status,
            decision.refusal or "refused",
            decision.detail,
            headers=headers,
            instance=instance,
        )

    try:
        attempt = await repo.create(
            session, owner=owner, scenario_version_id=version.id, mode=body.mode
        )
    except repo.AttemptLiveError:
        raise AppError(
            409, "active_attempt_exists", "You already have an incident running."
        ) from None
    # Commit before starting the workflow: its first activity reads this row.
    await session.commit()
    inp = LifecycleInput(
        attempt_id=str(attempt.id),
        scenario_slug=row.scenario.slug,
        tier=tier,
        ttl_minutes=decision.ttl_minutes,
        idle_minutes=decision.idle_minutes,
        extend_minutes=limits.extend_minutes,
        max_extends=limits.max_extends,
    )
    try:
        await _orchestrator(request).start(inp)
    except OrchestratorError as exc:
        log.error("attempt.start_failed", attempt_id=str(attempt.id), error=str(exc))
        await repo.move(
            session, attempt.id, AttemptState.FAILED, reason="could not start the sandbox"
        )
        await session.commit()
        raise AppError(
            503,
            "capacity",
            "Sandboxes are unavailable right now. Try again shortly.",
            headers={"Retry-After": "30"},
        ) from exc
    log.info("attempt.started", attempt_id=str(attempt.id), tier=tier, ttl=decision.ttl_minutes)
    response.headers["Location"] = f"/v1/attempts/{attempt.id}"
    return await _attempt_out(session, attempt)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
async def get_attempt(
    attempt_id: uuid.UUID, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> AttemptOut:
    attempt = await _owned(session, attempt_id, _owner(user, jti))
    return await _attempt_out(session, attempt)


async def _steer(
    request: Request, session: Any, attempt_id: uuid.UUID, owner: repo.Owner, signal: str
) -> AttemptOut:
    attempt = await _owned(session, attempt_id, owner)
    if attempt.state in TERMINAL_STATES:
        raise AppError(409, "attempt_ended", "This incident has already ended.")
    try:
        await _orchestrator(request).signal(str(attempt.id), signal)
        if signal != SIGNAL_ABANDON:
            await _orchestrator(request).signal(str(attempt.id), SIGNAL_TOUCH)
    except OrchestratorError as exc:
        raise AppError(
            503,
            "unavailable",
            "Could not reach the sandbox controller.",
            headers={"Retry-After": "10"},
        ) from exc
    return await _attempt_out(session, attempt)


@router.delete("/attempts/{attempt_id}", status_code=202, response_model=AttemptOut)
async def abandon_attempt(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> AttemptOut:
    """Abandon: the sandbox is torn down and the attempt ends."""
    return await _steer(request, session, attempt_id, _owner(user, jti), SIGNAL_ABANDON)


@router.post("/attempts/{attempt_id}/extend", status_code=202, response_model=AttemptOut)
async def extend_attempt(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> AttemptOut:
    """Ask for more time (granted within the plan; the outcome arrives as an `extend` event)."""
    return await _steer(request, session, attempt_id, _owner(user, jti), SIGNAL_EXTEND)


@router.post("/attempts/{attempt_id}/reset", status_code=202, response_model=AttemptOut)
async def reset_attempt(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> AttemptOut:
    """Rebuild the sandbox in its initial broken state (the session's deadline stays)."""
    return await _steer(request, session, attempt_id, _owner(user, jti), SIGNAL_RESET)


@router.post("/attempts/{attempt_id}/verify", status_code=202, response_model=AttemptOut)
async def verify_attempt(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> AttemptOut:
    """Run the verifier's probes against the sandbox (results arrive as a `verify` event).

    Idempotent: asking again while a run is in progress returns that run's attempt.
    """
    attempt = await _owned(session, attempt_id, _owner(user, jti))
    if attempt.state is AttemptState.VERIFYING:
        return await _attempt_out(session, attempt)
    if attempt.state is AttemptState.PROVISIONING:
        raise AppError(409, "not_ready", "The sandbox is still starting.")
    return await _steer(request, session, attempt_id, _owner(user, jti), SIGNAL_VERIFY)


@router.get(
    "/attempts/{attempt_id}/events",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-sent events"}},
)
async def attempt_events(
    attempt_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    """State changes and sandbox events as SSE. Resumable with Last-Event-ID."""
    await _owned(session, attempt_id, _owner(user, jti))
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    factory = request.app.state.session_factory
    valkey = request.app.state.valkey

    async def stream() -> AsyncIterator[ServerSentEvent]:
        nonlocal after
        pubsub = valkey.pubsub()
        await pubsub.subscribe(events_channel(str(attempt_id)))
        try:
            while not await request.is_disconnected():
                async with factory() as db:
                    events = await repo.events_after(db, attempt_id, after)
                    attempt = await repo.get(db, attempt_id)
                torn_down = False
                for event in events:
                    after = event.id
                    torn_down |= (
                        event.type == "sandbox" and event.payload.get("action") == "destroyed"
                    )
                    if not visible(event.type):
                        continue  # spoilers (which fault) and bookkeeping stay server-side
                    yield ServerSentEvent(
                        data=json.dumps(
                            {
                                "type": event.type,
                                "ts": event.ts.isoformat(),
                                "payload": event.payload,
                            }
                        ),
                        id=str(event.id),
                    )
                if attempt is None or torn_down:
                    return
                # Ended without a sandbox (it never started), or teardown is overdue: stop.
                if (
                    attempt.ended_at is not None
                    and not events
                    and (datetime.now(UTC) - attempt.ended_at).total_seconds()
                    > _SSE_TEARDOWN_GRACE_S
                ):
                    return
                # Sleep until the worker announces new events; poll anyway in case one was missed.
                await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=_SSE_PING_S),
                    _SSE_PING_S + 5,
                )
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return EventSourceResponse(stream(), ping=_SSE_PING_S)


@router.get("/me/usage", response_model=UsageOut, tags=["me"])
async def my_usage(
    session: SessionDep, settings: SettingsDep, user: OptionalUser, jti: GuestJti
) -> UsageOut:
    """Live incidents and sandbox minutes left this period; whether free starts are paused."""
    owner = _owner(user, jti)
    now = datetime.now(UTC)
    tier, limits = await _tier_and_limits(session, owner)
    usage = await _usage(session, owner, limits, now)
    fleet = await _fleet(session, settings, now)
    return UsageOut(
        tier=tier,
        live_starts=Quota(
            used=usage.starts_in_period,
            limit=limits.live_starts,
            period=limits.live_starts_period,
            resets_at=policy.next_rollover(now, limits.live_starts_period),
        ),
        sandbox_minutes=Quota(
            used=round(usage.minutes_in_period, 1),
            limit=limits.sandbox_minutes,
            period=limits.sandbox_minutes_period,
            resets_at=policy.next_rollover(now, limits.sandbox_minutes_period),
        ),
        session_minutes=limits.ttl_minutes,
        idle_minutes=limits.idle_minutes,
        free_paused=limits.budgeted
        and (
            not fleet.free_starts_enabled
            or fleet.budgeted_minutes_today >= fleet.daily_budget_minutes
        ),
    )
