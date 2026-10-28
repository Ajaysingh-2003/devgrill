"""The incident workspace: what to render, WebSocket tickets, hints and nudges, the war room
(teammates answer, ADR 016), the "declare mitigated" claim, and the sandbox operations behind
the panels (via the gateway).

Every endpoint checks that the caller owns the attempt (another player's attempt is a 404).
Sandbox operations also count as player activity for the idle timeout.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request, Response
from fastapi import Path as PathParam
from sqlalchemy import func, select

from devgrill.ai import coaching
from devgrill.ai.port import AiUnavailable, CallMeta
from devgrill.domain.attempt import TERMINAL_STATES
from devgrill.domain.enums import AttemptMode, AttemptState
from devgrill.domain.spec import ScenarioSpec
from devgrill.infra import assist as ai
from devgrill.infra.events import EventRecorder, fire_trigger
from devgrill.infra.models import (
    Attempt,
    AttemptEvent,
    SandboxSession,
    Scenario,
    ScenarioVersion,
    Track,
)
from devgrill.infra.repositories import attempts as repo
from devgrill.infra.signing import Ticket, issue_ticket
from devgrill.sandbox.content import Bundle, load_bundle
from devgrill.sandbox.lifecycle import SIGNAL_TOUCH
from devgrill_api import assist
from devgrill_api.deps import GuestJti, OptionalUser, SessionDep, SettingsDep
from devgrill_api.errors import AppError
from devgrill_api.gateway import Gateway, HttpGateway
from devgrill_api.orchestrator import OrchestratorError
from devgrill_api.routers.attempts import (
    _attempt_out,
    _orchestrator,
    _owned,
    _owner,
    _tier_and_limits,
)
from devgrill_api.schemas import (
    CacheOut,
    DbInsightsOut,
    DeployChangesOut,
    DeployHistoryOut,
    DeployIn,
    DeployOut,
    FileIn,
    FileOut,
    FileSaved,
    FilesOut,
    HintOut,
    MessageIn,
    MitigationOut,
    NudgeOut,
    PageOut,
    QueryIn,
    QueryOut,
    RestartIn,
    RestartOut,
    RollbackIn,
    SloTarget,
    StatusOut,
    TicketIn,
    TicketOut,
    WorkspaceOut,
)

log = structlog.get_logger(__name__)
router = APIRouter(tags=["workspace"])


@lru_cache(maxsize=64)
def _bundle(content_root: Path, slug: str) -> Bundle:
    return load_bundle(content_root, slug)


def _gateway(request: Request) -> Gateway:
    state = request.app.state
    if getattr(state, "gateway", None) is None:
        state.gateway = HttpGateway(state.settings)
    gateway: Gateway = state.gateway
    return gateway


def _recorder(request: Request) -> EventRecorder:
    return EventRecorder(request.app.state.session_factory, request.app.state.valkey)


async def _live(
    session: Any, attempt_id: uuid.UUID, user: OptionalUser, jti: str | None
) -> Attempt:
    attempt = await _owned(session, attempt_id, _owner(user, jti))
    if attempt.state in TERMINAL_STATES:
        raise AppError(409, "attempt_ended", "This drill has ended.")
    return attempt


def _owner_key(owner: repo.Owner) -> str:
    return f"user:{owner.user_id}" if owner.user_id else f"guest:{owner.guest_hash}"


async def _touch(request: Request, attempt_id: uuid.UUID) -> None:
    try:
        await _orchestrator(request).signal(str(attempt_id), SIGNAL_TOUCH)
    except OrchestratorError as exc:
        log.warning("workspace.touch_failed", attempt_id=str(attempt_id), error=str(exc))


async def _spec_and_slug(session: Any, attempt: Attempt) -> tuple[ScenarioSpec, Scenario, str]:
    row = (
        await session.execute(
            select(ScenarioVersion.spec, Scenario, Track.slug)
            .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
            .join(Track, Track.id == Scenario.track_id)
            .where(ScenarioVersion.id == attempt.scenario_version_id)
        )
    ).one()
    spec, scenario, track_slug = row
    return ScenarioSpec.model_validate(spec), scenario, track_slug


async def _events_of(session: Any, attempt_id: uuid.UUID, type_: str) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(AttemptEvent.payload)
        .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == type_)
        .order_by(AttemptEvent.id)
    )
    return [r for r in rows if isinstance(r, dict)]


# ------------------------------------------------------------------------------ workspace


@router.get("/attempts/{attempt_id}/workspace", response_model=WorkspaceOut)
async def get_workspace(
    attempt_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    user: OptionalUser,
    jti: GuestJti,
) -> WorkspaceOut:
    """Everything the workspace renders before its streams connect (ended attempts too)."""
    owner = _owner(user, jti)
    attempt = await _owned(session, attempt_id, owner)
    spec, scenario, track_slug = await _spec_and_slug(session, attempt)
    bundle = _bundle(settings.content_root, scenario.slug)
    _, limits = await _tier_and_limits(session, owner)
    hints = [
        HintOut(tier=int(h["tier"]), text=str(h["text"]))
        for h in await _events_of(session, attempt.id, "hint")
    ]
    granted = sum(1 for e in await _events_of(session, attempt.id, "extend") if e.get("granted"))
    resources = await session.scalar(
        select(SandboxSession.resources)
        .where(SandboxSession.attempt_id == attempt.id)
        .order_by(SandboxSession.created_at.desc())
        .limit(1)
    )
    idle = int((resources or {}).get("idle_minutes", limits.idle_minutes))
    slo = spec.slo.targets() if spec.slo else {}
    return WorkspaceOut(
        attempt=await _attempt_out(session, attempt),
        scenario_title=scenario.title,
        track_slug=track_slug,
        difficulty=scenario.difficulty,
        page=PageOut(severity=spec.page.severity, title=spec.page.title) if spec.page else None,
        unlocked_tools=list(spec.unlocked_tools),
        metrics=list(spec.charts) or list(bundle.base_app.metrics),
        slo={k: SloTarget(lt=v.lt, gt=v.gt) for k, v in slo.items()},
        deployable=bundle.base_app.patchable_services,
        hints_total=3 if spec.hints and attempt.mode is not AttemptMode.ONCALL else 0,
        hints=hints,
        extend_minutes=limits.extend_minutes,
        extends_left=max(0, limits.max_extends - granted),
        idle_minutes=idle,
        gateway_url=settings.gateway_public_url,
    )


@router.post("/attempts/{attempt_id}/ws-ticket", response_model=TicketOut, status_code=201)
async def create_ws_ticket(
    attempt_id: uuid.UUID,
    body: TicketIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: OptionalUser,
    jti: GuestJti,
) -> TicketOut:
    """A single-use, one-minute ticket for the terminal or telemetry WebSocket."""
    attempt = await _live(session, attempt_id, user, jti)
    ticket = await issue_ticket(
        request.app.state.valkey,
        Ticket(attempt_id=str(attempt.id), kind=body.kind, owner=_owner_key(_owner(user, jti))),
        settings.ws_ticket_ttl_s,
    )
    base = settings.gateway_public_url.rstrip("/")
    url = f"{base}/gw/v1/attempts/{attempt.id}/{body.kind}?ticket={ticket}"
    return TicketOut(ticket=ticket, url=url, expires_in=settings.ws_ticket_ttl_s)


# ----------------------------------------------------------------------- hints, war room


@router.get("/attempts/{attempt_id}/hints", response_model=list[HintOut])
async def list_hints(
    attempt_id: uuid.UUID, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> list[HintOut]:
    attempt = await _owned(session, attempt_id, _owner(user, jti))
    return [
        HintOut(tier=int(h["tier"]), text=str(h["text"]))
        for h in await _events_of(session, attempt.id, "hint")
    ]


@router.post("/attempts/{attempt_id}/hints", response_model=HintOut, status_code=201)
async def take_hint(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> HintOut:
    """Reveal the next hint tier (1 nudge, 2 direction, 3 near-answer). Hint use is scored."""
    attempt = await _live(session, attempt_id, user, jti)
    spec, _, _ = await _spec_and_slug(session, attempt)
    if spec.hints is None:
        raise AppError(404, "no_hints", "This drill has no hints.")
    if attempt.mode is AttemptMode.ONCALL:
        raise AppError(409, "no_hints_on_call", "You're playing without hints this time.")
    taken = await session.scalar(
        select(func.count())
        .select_from(AttemptEvent)
        .where(AttemptEvent.attempt_id == attempt.id, AttemptEvent.type == "hint")
    )
    tier = int(taken or 0) + 1
    if tier > 3:
        raise AppError(409, "no_more_hints", "You've seen every hint for this drill.")
    text = {1: spec.hints.tier1, 2: spec.hints.tier2, 3: spec.hints.tier3}[tier]
    attempt.hints_used = tier
    await repo.add_event(session, attempt.id, "hint", {"tier": tier, "text": text})
    await fire_trigger(session, attempt.id, f"hint:{tier}")
    await session.commit()
    await _recorder(request).announce(attempt.id)
    await _touch(request, attempt.id)
    return HintOut(tier=tier, text=text)


@router.post("/attempts/{attempt_id}/messages", status_code=204)
async def post_message(
    attempt_id: uuid.UUID,
    body: MessageIn,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> Response:
    """A status update from the player to the war room. A teammate replies over the event
    stream (`assist` events, then a `reply` event) when AI is on and the plan allows it."""
    attempt = await _live(session, attempt_id, user, jti)
    owner = _owner(user, jti)
    spec, _, _ = await _spec_and_slug(session, attempt)
    _, limits = await _tier_and_limits(session, owner)
    await session.commit()
    text = body.text.strip()
    await _recorder(request).record(attempt.id, "message", {"author": "you", "text": text})
    await _touch(request, attempt.id)
    state = request.app.state
    if "war_room" in spec.unlocked_tools and assist.llm_of(state).enabled("persona"):
        allowed = await assist.take_allowance(
            state.valkey, _owner_key(owner), limits.ai_messages_per_day, datetime.now(UTC)
        )
        if allowed:
            assist.spawn(state, assist.answer(state, attempt.id, owner.user_id, text))
        else:
            await assist.busy(state, attempt.id, assist.OVER_ALLOWANCE)
    return Response(status_code=204)


#: Modes with a coach at your shoulder; on-call and challenges are played alone.
NUDGE_MODES = frozenset({AttemptMode.GUIDED, AttemptMode.TUTORIAL})


@router.post("/attempts/{attempt_id}/nudge", response_model=NudgeOut, status_code=201)
async def nudge(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> NudgeOut:
    """Guided mode: a nudge toward the next step from what the player has done so far. It
    leans on the next hint without giving it away, and costs no score."""
    attempt = await _live(session, attempt_id, user, jti)
    if attempt.mode not in NUDGE_MODES:
        raise AppError(409, "no_nudges", "Nudges are for runs with hints.")
    state = request.app.state
    llm = assist.llm_of(state)
    if not llm.enabled("nudge"):
        raise AppError(503, "ai_unavailable", assist.BUSY)
    owner = _owner(user, jti)
    _, limits = await _tier_and_limits(session, owner)
    if not await assist.take_allowance(
        state.valkey, _owner_key(owner), limits.ai_messages_per_day, datetime.now(UTC)
    ):
        raise AppError(429, "ai_allowance", assist.OVER_ALLOWANCE)
    v = await ai.view(session, attempt.id)
    assert v is not None
    ctx = await ai.persona_context(session, v)
    await session.commit()  # release the connection for the model call
    locked = [] if len(ctx.hints) >= v.spec.ai.reveal_at else v.spec.ai.spoilers
    try:
        text = await coaching.nudge(
            llm,
            title=ctx.title,
            story=ctx.story,
            direction=ai.nudge_direction(v.spec, len(ctx.hints)),
            trail=ctx.trail,
            spoilers=locked,
            meta=CallMeta("nudge", owner.user_id, attempt.id),
        )
    except AiUnavailable as exc:
        log.info("workspace.nudge_unavailable", attempt_id=str(attempt.id), reason=exc.reason)
        raise AppError(503, "ai_unavailable", assist.BUSY) from exc
    await _recorder(request).record(attempt.id, "nudge", {"text": text})
    await _touch(request, attempt.id)
    return NudgeOut(text=text)


@router.post("/attempts/{attempt_id}/touch", status_code=204)
async def touch_attempt(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> Response:
    """The player is here (reading counts): resets the idle timeout. Sent at most once a minute."""
    attempt = await _live(session, attempt_id, user, jti)
    await _touch(request, attempt.id)
    return Response(status_code=204)


@router.post("/attempts/{attempt_id}/mitigation", response_model=MitigationOut)
async def declare_mitigated(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> MitigationOut:
    """Declare the incident mitigated; the claim is checked against the detected state."""
    attempt = await _live(session, attempt_id, user, jti)
    correct = attempt.state is AttemptState.MITIGATED
    await session.commit()
    await _recorder(request).record(
        attempt.id,
        "mitigation",
        {"declared": True, "real_state": attempt.state.value, "correct": correct},
    )
    return MitigationOut(declared=True, real_state=attempt.state, correct=correct)


# --------------------------------------------------------------------- sandbox operations


async def _op(
    request: Request,
    session: Any,
    attempt_id: uuid.UUID,
    user: OptionalUser,
    jti: str | None,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt = await _live(session, attempt_id, user, jti)
    await session.commit()  # release the connection: some operations take seconds
    result = await _gateway(request).call(method, attempt.id, path, query=query, body=body)
    await _touch(request, attempt.id)
    return result


@router.get("/attempts/{attempt_id}/status", response_model=StatusOut)
async def sandbox_status(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> StatusOut:
    return StatusOut.model_validate(
        await _op(request, session, attempt_id, user, jti, "GET", "status")
    )


@router.get("/attempts/{attempt_id}/files", response_model=FilesOut)
async def list_files(
    attempt_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
    service: str | None = Query(default=None, max_length=40),
) -> FilesOut:
    query = {"service": service} if service else None
    return FilesOut.model_validate(
        await _op(request, session, attempt_id, user, jti, "GET", "files", query=query)
    )


def _file_query(path: str, service: str | None) -> dict[str, str]:
    return {"path": path, **({"service": service} if service else {})}


@router.get("/attempts/{attempt_id}/file", response_model=FileOut)
async def read_file(
    attempt_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
    path: str = Query(min_length=1, max_length=300),
    service: str | None = Query(default=None, max_length=40),
) -> FileOut:
    data = await _op(
        request, session, attempt_id, user, jti, "GET", "file", query=_file_query(path, service)
    )
    return FileOut.model_validate(data)


@router.put("/attempts/{attempt_id}/file", response_model=FileSaved)
async def write_file(
    attempt_id: uuid.UUID,
    body: FileIn,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
    path: str = Query(min_length=1, max_length=300),
    service: str | None = Query(default=None, max_length=40),
) -> FileSaved:
    data = await _op(
        request,
        session,
        attempt_id,
        user,
        jti,
        "PUT",
        "file",
        query=_file_query(path, service),
        body={"content": body.content},
    )
    return FileSaved.model_validate(data)


@router.get("/attempts/{attempt_id}/deploys", response_model=DeployHistoryOut)
async def list_deploys(
    attempt_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
    service: str | None = Query(default=None, max_length=40),
) -> DeployHistoryOut:
    query = {"service": service} if service else None
    data = await _op(request, session, attempt_id, user, jti, "GET", "deploys", query=query)
    return DeployHistoryOut.model_validate(data)


@router.get("/attempts/{attempt_id}/deploys/{sha}", response_model=DeployChangesOut)
async def deploy_changes(
    attempt_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
    sha: str = PathParam(pattern=r"^[0-9a-f]{4,40}$"),
    service: str | None = Query(default=None, max_length=40),
) -> DeployChangesOut:
    """What one deploy in the history changed (files and diff), as `git show` would print."""
    query = {"service": service} if service else None
    data = await _op(request, session, attempt_id, user, jti, "GET", f"deploys/{sha}", query=query)
    return DeployChangesOut.model_validate(data)


@router.post("/attempts/{attempt_id}/deploys", response_model=DeployOut)
async def deploy(
    attempt_id: uuid.UUID,
    body: DeployIn,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> DeployOut:
    """Deploy a service's working tree; it restarts, and `ok` says whether it came back healthy."""
    data = await _op(
        request, session, attempt_id, user, jti, "POST", "deploys", body={"service": body.service}
    )
    return DeployOut.model_validate(data)


@router.post("/attempts/{attempt_id}/rollbacks", response_model=DeployOut)
async def rollback(
    attempt_id: uuid.UUID,
    body: RollbackIn,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> DeployOut:
    """Deploy an earlier commit (the working tree is left as it is)."""
    data = await _op(
        request,
        session,
        attempt_id,
        user,
        jti,
        "POST",
        "rollbacks",
        body={"service": body.service, "ref": body.ref},
    )
    return DeployOut.model_validate(data)


@router.post("/attempts/{attempt_id}/restarts", response_model=RestartOut)
async def restart_service(
    attempt_id: uuid.UUID,
    body: RestartIn,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> RestartOut:
    data = await _op(
        request, session, attempt_id, user, jti, "POST", "restarts", body={"service": body.service}
    )
    return RestartOut.model_validate(data)


@router.get("/attempts/{attempt_id}/db", response_model=DbInsightsOut)
async def db_insights(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> DbInsightsOut:
    """Busiest statements, connections by state, sessions waiting on locks."""
    return DbInsightsOut.model_validate(
        await _op(request, session, attempt_id, user, jti, "GET", "db")
    )


@router.post("/attempts/{attempt_id}/db/query", response_model=QueryOut)
async def db_query(
    attempt_id: uuid.UUID,
    body: QueryIn,
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> QueryOut:
    """One read-only statement (read-only role and transaction, 5 s timeout, 200 rows)."""
    data = await _op(
        request, session, attempt_id, user, jti, "POST", "db/query", body={"sql": body.sql}
    )
    return QueryOut.model_validate(data)


@router.get("/attempts/{attempt_id}/cache", response_model=CacheOut)
async def cache_insights(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> CacheOut:
    """Hit rate and memory, a sample of stored keys, and the keys clients ask for."""
    return CacheOut.model_validate(
        await _op(request, session, attempt_id, user, jti, "GET", "cache")
    )
