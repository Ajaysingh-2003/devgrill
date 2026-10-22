"""After the incident (ADR 015): the debrief, and the postmortem editor's document.

The AI's part (ADR 016): a coach note and the approach's reading come from the worker after
settling; a submitted postmortem is reviewed by the PostmortemReview workflow, within the
plan's allowance (guests aren't reviewed).

Both belong to the attempt's owner (another player's attempt is a 404) and exist once the
attempt has ended. The debrief reads what the worker settled (score, rating, approach) and
rebuilds the investigation replay from the trail with the scenario's markers. Known
approaches are spoilers: they appear only to players who have resolved the scenario.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from devgrill.domain import entitlements as policy
from devgrill.domain import postmortem as pm
from devgrill.domain.attempt import TERMINAL_STATES
from devgrill.domain.debrief import REPLAY_TYPES, TrailEvent, replay
from devgrill.domain.enums import AttemptState, ScenarioStatus
from devgrill.domain.spec import ScenarioSpec
from devgrill.infra import assist as ai
from devgrill.infra.models import (
    Approach,
    Attempt,
    AttemptEvent,
    Postmortem,
    PostmortemGrade,
    Scenario,
    ScenarioVersion,
    Track,
    VerifyRun,
)
from devgrill.infra.repositories import attempts as repo
from devgrill.infra.repositories import catalog
from devgrill.infra.settle import summarise_run
from devgrill_api.assist import llm_of
from devgrill_api.deps import GuestJti, OptionalUser, SessionDep
from devgrill_api.errors import AppError
from devgrill_api.orchestrator import OrchestratorError
from devgrill_api.routers.attempts import (
    _attempt_out,
    _orchestrator,
    _owned,
    _owner,
    _tier_and_limits,
)
from devgrill_api.schemas import (
    ApproachNoteOut,
    CoachNoteOut,
    CriterionReviewOut,
    DebriefApproachOut,
    DebriefOut,
    MasteryOut,
    NextDrillOut,
    PostmortemIn,
    PostmortemOut,
    PostmortemReviewOut,
    ProbeResultOut,
    RatingChangeOut,
    ReplayEntryOut,
    ScoreOut,
    SloTarget,
    VerifyRunOut,
)

router = APIRouter(tags=["debrief"])


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
            select(AttemptEvent.id, AttemptEvent.ts, AttemptEvent.type, AttemptEvent.payload)
            .where(AttemptEvent.attempt_id == attempt.id, AttemptEvent.type.in_(REPLAY_TYPES))
            .order_by(AttemptEvent.id)
        )
    ).all()
    entries = replay(
        [TrailEvent(ts, type_, payload or {}, id_) for id_, ts, type_, payload in rows],
        attempt.active_at,
        spec.replay,
    )
    return [
        ReplayEntryOut(at_s=e.at_s, text=e.text, mark=e.mark, note=e.note, event_id=e.event_id)
        for e in entries
    ]


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
    coach = (score or {}).get("coach")
    reading = (score or {}).get("approach")
    approach_note = None
    if isinstance(reading, dict) and reading.get("source") == "ai":
        approach_note = ApproachNoteOut(
            source="ai",
            confidence=reading.get("confidence"),
            rationale=reading.get("rationale") if resolved else None,
        )
    elif yours_key is not None:
        approach_note = ApproachNoteOut(source="rules", confidence=attempt.approach_confidence)
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
        coach=CoachNoteOut(text=coach["text"], cites=list(coach.get("cites", [])))
        if isinstance(coach, dict)
        else None,
        approach_note=approach_note,
        review=await _review(session, doc, spec),
    )


# ---------------------------------------------------------------------------- postmortem


async def _timeline(session: Any, attempt: Attempt, spec: ScenarioSpec) -> list[str]:
    return [f"{pm.clock(e.at_s)} {e.text}" for e in await _replay(session, attempt, spec)]


async def _review(
    session: Any, doc: Postmortem | None, spec: ScenarioSpec
) -> PostmortemReviewOut | None:
    """Where the AI review of a submitted postmortem stands."""
    if doc is None or doc.submitted_at is None:
        return None
    grade = await session.scalar(
        select(PostmortemGrade)
        .where(PostmortemGrade.postmortem_id == doc.id)
        .order_by(PostmortemGrade.created_at.desc())
        .limit(1)
    )
    if grade is not None:
        s = grade.scores
        described = {c.key: c.description for c in ai.rubric(spec)}
        return PostmortemReviewOut(
            status="graded",
            criteria=[
                CriterionReviewOut(
                    key=c["key"],
                    description=described.get(c["key"]) or str(c["key"]),
                    score=c["score"],
                    max=c["max"],
                    evidence=c["evidence"],
                    reason=c["reason"],
                    unsupported=c["unsupported"],
                )
                for c in s.get("criteria", [])
            ],
            total=s.get("total"),
            max=s.get("max"),
            fraction=s.get("fraction"),
            blameless=s.get("blameless"),
            blame=s.get("blame", []),
            feedback=grade.feedback_md,
            graded_at=grade.created_at,
        )
    last = await session.scalar(
        select(AttemptEvent.payload)
        .where(AttemptEvent.attempt_id == doc.attempt_id, AttemptEvent.type == "review")
        .order_by(AttemptEvent.id.desc())
        .limit(1)
    )
    status = (last or {}).get("status")
    if status in ("requested", "graded"):
        return PostmortemReviewOut(status="pending")
    if status == "failed":
        return PostmortemReviewOut(status="failed", detail=(last or {}).get("detail"))
    return PostmortemReviewOut(
        status="unavailable", detail=(last or {}).get("detail") or "Not reviewed."
    )


async def _reviews_used(session: Any, user_id: uuid.UUID, since: datetime | None) -> int:
    stmt = (
        select(func.count())
        .select_from(PostmortemGrade)
        .join(Postmortem, Postmortem.id == PostmortemGrade.postmortem_id)
        .join(Attempt, Attempt.id == Postmortem.attempt_id)
        .where(Attempt.user_id == user_id)
    )
    if since is not None:
        stmt = stmt.where(PostmortemGrade.created_at >= since)
    return int(await session.scalar(stmt) or 0)


async def _request_review(request: Request, session: Any, attempt: Attempt) -> None:
    """Ask the worker to grade the postmortem, or record why it won't be."""

    async def note(status: str, detail: str | None = None) -> None:
        await repo.add_event(session, attempt.id, "review", {"status": status, "detail": detail})
        await session.commit()

    if attempt.user_id is None:
        return await note("unavailable", "Sign in to get your postmortems reviewed.")
    if not llm_of(request.app.state).enabled("grade"):
        return await note("unavailable", "Reviews are off right now. Try again later.")
    _, limits = await _tier_and_limits(session, repo.Owner(user_id=attempt.user_id))
    if limits.postmortem_reviews == 0:
        return await note("unavailable", "Postmortem reviews aren't part of your plan.")
    since = policy.period_start(datetime.now(UTC), limits.postmortem_reviews_period)
    if await _reviews_used(session, attempt.user_id, since) >= limits.postmortem_reviews:
        period = {"day": "today", "week": "this week"}.get(limits.postmortem_reviews_period, "")
        return await note(
            "unavailable", f"You've used your {limits.postmortem_reviews} reviews {period}."
        )
    await note("requested")
    try:
        await _orchestrator(request).review(str(attempt.id))
    except OrchestratorError:
        await note("failed", "The review couldn't start. Try again in a minute.")


def _postmortem_out(
    doc: Postmortem | None,
    timeline: list[str],
    scenario: Scenario,
    review: PostmortemReviewOut | None = None,
) -> PostmortemOut:
    sections = pm.from_markdown(doc.body_md) if doc is not None else pm.from_markdown("")
    return PostmortemOut(
        scenario_title=scenario.title,
        sections=sections,  # type: ignore[arg-type]
        timeline=timeline,
        submitted_at=doc.submitted_at if doc else None,
        updated_at=doc.updated_at if doc else None,
        review=review,
    )


@router.get("/attempts/{attempt_id}/postmortem", response_model=PostmortemOut)
async def get_postmortem(
    attempt_id: uuid.UUID, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> PostmortemOut:
    """The draft (or submitted) postmortem, and the timeline that goes with it."""
    attempt = await _ended(session, attempt_id, user, jti)
    spec, scenario, _ = await _context(session, attempt)
    doc = await session.scalar(select(Postmortem).where(Postmortem.attempt_id == attempt.id))
    timeline = await _timeline(session, attempt, spec)
    return _postmortem_out(doc, timeline, scenario, await _review(session, doc, spec))


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
    request: Request,
    session: SessionDep,
    user: OptionalUser,
    jti: GuestJti,
) -> PostmortemOut:
    """Submit: the timeline is added, the document is frozen, and the AI review starts (when
    the plan includes reviews). The review's progress is in `review`."""
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
    await _request_review(request, session, attempt)
    return _postmortem_out(doc, timeline, scenario, await _review(session, doc, spec))


@router.post(
    "/attempts/{attempt_id}/postmortem/review",
    response_model=PostmortemReviewOut,
    status_code=202,
)
async def review_postmortem(
    attempt_id: uuid.UUID, request: Request, session: SessionDep, user: OptionalUser, jti: GuestJti
) -> PostmortemReviewOut:
    """Ask again for a review that failed or wasn't available (a pending one is returned)."""
    attempt = await _ended(session, attempt_id, user, jti)
    spec, _, _ = await _context(session, attempt)
    doc = await session.scalar(select(Postmortem).where(Postmortem.attempt_id == attempt.id))
    current = await _review(session, doc, spec)
    if current is None:
        raise AppError(409, "not_submitted", "Submit the postmortem first.")
    if current.status == "graded":
        raise AppError(409, "already_reviewed", "This postmortem has been reviewed.")
    if current.status == "pending":
        return current
    await _request_review(request, session, attempt)
    review = await _review(session, doc, spec)
    assert review is not None
    return review
