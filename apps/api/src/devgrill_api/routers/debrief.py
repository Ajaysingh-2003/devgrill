"""After the incident (ADR 015): the debrief, and the postmortem editor's document.

Both belong to the attempt's owner (another player's attempt is a 404) and exist once the
attempt has ended. The debrief reads what the worker settled (score, rating, approach) and
rebuilds the investigation replay from the trail with the scenario's markers. Known
approaches are spoilers: they appear only to players who have resolved the scenario.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from devgrill.domain import postmortem as pm
from devgrill.domain.attempt import TERMINAL_STATES
from devgrill.domain.debrief import TrailEvent, replay
from devgrill.domain.enums import AttemptState, ScenarioStatus
from devgrill.domain.spec import ScenarioSpec
from devgrill.infra.models import (
    Approach,
    Attempt,
    AttemptEvent,
    Postmortem,
    Scenario,
    ScenarioVersion,
    Track,
    VerifyRun,
)
from devgrill.infra.repositories import catalog
from devgrill.infra.settle import summarise_run
from devgrill_api.deps import GuestJti, OptionalUser, SessionDep
from devgrill_api.errors import AppError
from devgrill_api.routers.attempts import _attempt_out, _owned, _owner
from devgrill_api.schemas import (
    DebriefApproachOut,
    DebriefOut,
    MasteryOut,
    NextDrillOut,
    PostmortemIn,
    PostmortemOut,
    ProbeResultOut,
    RatingChangeOut,
    ReplayEntryOut,
    ScoreOut,
    SloTarget,
    VerifyRunOut,
)

router = APIRouter(tags=["debrief"])

#: Event types the replay reads (others are bookkeeping or teammates' lines).
REPLAY_TYPES = (
    "alert",
    "action",
    "deploy",
    "rollback",
    "trail",
    "hint",
    "message",
    "mitigation",
    "state",
    "verify",
)


async def _ended(
    session: Any, attempt_id: uuid.UUID, user: OptionalUser, jti: str | None
) -> Attempt:
    attempt = await _owned(session, attempt_id, _owner(user, jti))
    if attempt.state not in TERMINAL_STATES:
        raise AppError(409, "still_live", "The debrief opens when the incident ends.")
    return attempt


async def _context(session: Any, attempt: Attempt) -> tuple[ScenarioSpec, Scenario, Track]:
    spec, scenario, track = (
        await session.execute(
            select(ScenarioVersion.spec, Scenario, Track)
            .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
            .join(Track, Track.id == Scenario.track_id)
            .where(ScenarioVersion.id == attempt.scenario_version_id)
        )
    ).one()
    return ScenarioSpec.model_validate(spec), scenario, track


async def _replay(session: Any, attempt: Attempt, spec: ScenarioSpec) -> list[ReplayEntryOut]:
    rows = (
        await session.execute(
            select(AttemptEvent.ts, AttemptEvent.type, AttemptEvent.payload)
            .where(AttemptEvent.attempt_id == attempt.id, AttemptEvent.type.in_(REPLAY_TYPES))
            .order_by(AttemptEvent.id)
        )
    ).all()
    entries = replay(
        [TrailEvent(ts, type_, payload or {}) for ts, type_, payload in rows],
        attempt.active_at,
        spec.replay,
    )
    return [ReplayEntryOut(at_s=e.at_s, text=e.text, mark=e.mark, note=e.note) for e in entries]


def _verify_out(run: VerifyRun, spec: ScenarioSpec) -> VerifyRunOut:
    targets = {p.key: p.target for p in spec.probes}
    summary = summarise_run(run)
    return VerifyRunOut(
        id=run.id,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        resolution=summary.resolution if summary else 0.0,
        probes=[
            ProbeResultOut(
                key=p["key"],
                title=p.get("title", p["key"]),
                how=p.get("how", ""),
                kind=p.get("kind", ""),
                passed=p.get("passed"),
                detail=p.get("detail", ""),
                measured=p.get("measured") or {},
                target={
                    k: SloTarget(lt=v.lt, gt=v.gt) for k, v in targets.get(p["key"], {}).items()
                },
                seconds=p.get("seconds"),
            )
            for p in (run.summary or {}).get("probes", [])
        ],
    )


async def _best_run(session: Any, attempt: Attempt, best_id: str | None) -> VerifyRun | None:
    if best_id:
        run = await session.get(VerifyRun, uuid.UUID(best_id))
        if run is not None:
            return run
    return await session.scalar(
        select(VerifyRun)
        .where(VerifyRun.attempt_id == attempt.id)
        .order_by(VerifyRun.created_at.desc())
        .limit(1)
    )


async def _next(session: Any, user_id: uuid.UUID | None, scenario: Scenario) -> list[NextDrillOut]:
    rows = (
        await session.execute(
            select(Scenario, Track.slug)
            .join(Track, Track.id == Scenario.track_id)
            .where(
                Scenario.track_id == scenario.track_id,
                Scenario.id != scenario.id,
                Scenario.status == ScenarioStatus.PUBLISHED,
            )
            .order_by(Scenario.difficulty.desc(), Scenario.est_minutes)
        )
    ).all()
    out: list[NextDrillOut] = []
    for s, track_slug in rows:
        if user_id is not None and await catalog.has_resolved(session, user_id, s.id):
            continue
        out.append(
            NextDrillOut(
                slug=s.slug,
                title=s.title,
                track_slug=track_slug,
                difficulty=s.difficulty,
                est_minutes=s.est_minutes,
            )
        )
        if len(out) == 3:
            break
    return out


async def _mastery(session: Any, attempt: Attempt, scenario: Scenario) -> MasteryOut | None:
    """Track mastery after this attempt, and before it (if it was a first resolution)."""
    if attempt.user_id is None:
        return None
    total = await session.scalar(
        select(func.count())
        .select_from(Scenario)
        .where(Scenario.track_id == scenario.track_id, Scenario.status == ScenarioStatus.PUBLISHED)
    )
    if not total:
        return None
    resolved = (
        select(ScenarioVersion.scenario_id)
        .join(Attempt, Attempt.scenario_version_id == ScenarioVersion.id)
        .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
        .where(
            Attempt.user_id == attempt.user_id,
            Attempt.state == AttemptState.RESOLVED,
            Scenario.track_id == scenario.track_id,
            Scenario.status == ScenarioStatus.PUBLISHED,
        )
    )
    solved = await session.scalar(
        select(func.count(func.distinct(resolved.subquery().c.scenario_id)))
    )
    earlier = await session.scalar(
        select(func.count())
        .select_from(Attempt)
        .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
        .where(
            Attempt.user_id == attempt.user_id,
            ScenarioVersion.scenario_id == scenario.id,
            Attempt.state == AttemptState.RESOLVED,
            Attempt.id != attempt.id,
            Attempt.resolved_at < (attempt.resolved_at or datetime.max.replace(tzinfo=UTC)),
        )
    )
    after = round(100 * int(solved or 0) / int(total))
    first = attempt.state is AttemptState.RESOLVED and not earlier
    before = round(100 * (int(solved or 0) - (1 if first else 0)) / int(total))
    return MasteryOut(before=max(0, before), after=after)


async def _shares(session: Any, scenario: Scenario) -> dict[uuid.UUID, int]:
    rows = (
        await session.execute(
            select(Attempt.approach_id, func.count())
            .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
            .where(
                ScenarioVersion.scenario_id == scenario.id,
                Attempt.state == AttemptState.RESOLVED,
            )
            .group_by(Attempt.approach_id)
        )
    ).all()
    total = sum(n for _, n in rows)
    return {aid: round(100 * n / total) for aid, n in rows if aid is not None and total}


@router.get("/attempts/{attempt_id}/debrief", response_model=DebriefOut)
async def get_debrief(
    attempt_id: uuid.UUID, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> DebriefOut:
    """What happened, how verify judged the fix, the score and rating, what to try next."""
    attempt = await _ended(session, attempt_id, user, jti)
    spec, scenario, track = await _context(session, attempt)
    score = attempt.score or None
    run = await _best_run(session, attempt, (score or {}).get("best_run_id"))

    rating = None
    if attempt.rating_delta:
        d = attempt.rating_delta
        rating = RatingChangeOut(
            track_slug=track.slug,
            track_title=track.title,
            before=d["before"]["rating"],
            after=d["after"]["rating"],
            delta=d["delta"],
            expected=d["expected"],
            outcome=d["outcome"],
        )

    yours_key = None
    if attempt.approach_id is not None:
        yours_key = await session.scalar(
            select(Approach.key).where(Approach.id == attempt.approach_id)
        )
    resolved = attempt.state is AttemptState.RESOLVED or (
        attempt.user_id is not None
        and await catalog.has_resolved(session, attempt.user_id, scenario.id)
    )
    approaches = None
    if resolved:
        shares = await _shares(session, scenario)
        approaches = [
            DebriefApproachOut(
                key=a.key,
                name=a.name,
                outcome=a.outcome,
                idea_md=a.idea_md,
                pros=list(a.pros),
                cons=list(a.cons),
                patch=a.exemplar_patch,
                yours=a.key == yours_key,
                share=shares.get(a.id, 0),
            )
            for a in await catalog.approaches(session, scenario.id)
        ]

    doc = await session.scalar(select(Postmortem).where(Postmortem.attempt_id == attempt.id))
    return DebriefOut(
        attempt=await _attempt_out(session, attempt),
        scenario_title=scenario.title,
        track_slug=track.slug,
        track_title=track.title,
        settled=score is not None,
        score=ScoreOut.model_validate(score) if score else None,
        rating=rating,
        mastery=await _mastery(session, attempt, scenario),
        verify=_verify_out(run, spec) if run is not None else None,
        approach_key=yours_key,
        approaches=approaches,
        replay=await _replay(session, attempt, spec),
        next=await _next(session, attempt.user_id, scenario),
        postmortem="none" if doc is None else ("submitted" if doc.submitted_at else "draft"),
    )


# ---------------------------------------------------------------------------- postmortem


async def _timeline(session: Any, attempt: Attempt, spec: ScenarioSpec) -> list[str]:
    return [f"{pm.clock(e.at_s)} {e.text}" for e in await _replay(session, attempt, spec)]


def _postmortem_out(
    doc: Postmortem | None, timeline: list[str], scenario: Scenario
) -> PostmortemOut:
    sections = pm.from_markdown(doc.body_md) if doc is not None else pm.from_markdown("")
    return PostmortemOut(
        scenario_title=scenario.title,
        sections=sections,  # type: ignore[arg-type]
        timeline=timeline,
        submitted_at=doc.submitted_at if doc else None,
        updated_at=doc.updated_at if doc else None,
    )


@router.get("/attempts/{attempt_id}/postmortem", response_model=PostmortemOut)
async def get_postmortem(
    attempt_id: uuid.UUID, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> PostmortemOut:
    """The draft (or submitted) postmortem, and the timeline that goes with it."""
    attempt = await _ended(session, attempt_id, user, jti)
    spec, scenario, _ = await _context(session, attempt)
    doc = await session.scalar(select(Postmortem).where(Postmortem.attempt_id == attempt.id))
    return _postmortem_out(doc, await _timeline(session, attempt, spec), scenario)


@router.put("/attempts/{attempt_id}/postmortem", response_model=PostmortemOut)
async def save_postmortem(
    attempt_id: uuid.UUID,
    body: PostmortemIn,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> PostmortemOut:
    """Save the draft. A submitted postmortem is final (409)."""
    attempt = await _ended(session, attempt_id, user, jti)
    spec, scenario, _ = await _context(session, attempt)
    doc = await session.scalar(
        select(Postmortem).where(Postmortem.attempt_id == attempt.id).with_for_update()
    )
    if doc is not None and doc.submitted_at is not None:
        raise AppError(409, "already_submitted", "This postmortem has been submitted.")
    body_md = pm.to_markdown({str(k): v for k, v in body.sections.items()})
    if doc is None:
        doc = Postmortem(attempt_id=attempt.id, body_md=body_md)
        session.add(doc)
    else:
        doc.body_md = body_md
    await session.commit()
    await session.refresh(doc)
    return _postmortem_out(doc, await _timeline(session, attempt, spec), scenario)


@router.post("/attempts/{attempt_id}/postmortem/submit", response_model=PostmortemOut)
async def submit_postmortem(
    attempt_id: uuid.UUID,
    body: PostmortemIn,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> PostmortemOut:
    """Submit for review: the timeline is added and the document is frozen (graded in phase 6)."""
    attempt = await _ended(session, attempt_id, user, jti)
    spec, scenario, _ = await _context(session, attempt)
    if not any(v.strip() for v in body.sections.values()):
        raise AppError(422, "empty_postmortem", "Write at least one section before submitting.")
    doc = await session.scalar(
        select(Postmortem).where(Postmortem.attempt_id == attempt.id).with_for_update()
    )
    if doc is not None and doc.submitted_at is not None:
        raise AppError(409, "already_submitted", "This postmortem has been submitted.")
    timeline = await _timeline(session, attempt, spec)
    body_md = pm.to_markdown({str(k): v for k, v in body.sections.items()}, timeline)
    if doc is None:
        doc = Postmortem(attempt_id=attempt.id, body_md=body_md)
        session.add(doc)
    else:
        doc.body_md = body_md
    doc.submitted_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(doc)
    return _postmortem_out(doc, timeline, scenario)
