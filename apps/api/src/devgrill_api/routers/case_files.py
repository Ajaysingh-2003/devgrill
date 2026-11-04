"""Case files (ADR 013, ADR 018): recorded incidents, free for everyone, with no sandbox.

A case file is read from the content folder like a scenario's bundle: `case.yaml` for the
questions and `evidence.json` for the recording. A retired scenario's case file goes with it.
Questions go out without their answers. A signed-in player's first answers are kept and count
as the day's activity; after them the answers are known, so a second try changes nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, cast

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi import Path as PathParam

from devgrill.ai import coaching
from devgrill.ai.port import AiUnavailable, CallMeta
from devgrill.domain import casefile
from devgrill.domain import entitlements as policy
from devgrill.domain.spec import CaseEvidence, CaseFileSpec, ScenarioSpec
from devgrill.domain.streaks import DEFAULT_TIMEZONE, activity_day
from devgrill.infra.models import CaseFilePlay
from devgrill.infra.repositories import casefiles as repo
from devgrill.infra.repositories import progress
from devgrill.sandbox.content import (
    ContentError,
    evidence_path,
    find_scenario,
    load_case_spec,
    load_evidence,
)
from devgrill_api.assist import llm_of
from devgrill_api.deps import OptionalUser, SessionDep, SettingsDep, User
from devgrill_api.errors import AppError
from devgrill_api.ratelimit import rate_limit
from devgrill_api.routers.attempts import _owner, _tier_and_limits
from devgrill_api.routers.workspace import _bundle
from devgrill_api.schemas import (
    CaseAnswerOut,
    CaseAnswersIn,
    CaseBeatOut,
    CaseClueOut,
    CaseEvidenceOut,
    CaseFileList,
    CaseFileOut,
    CaseFileSummary,
    CaseOptionOut,
    CaseQuestionOut,
    CaseResultOut,
    CaseReviewIn,
    CaseReviewOut,
    PageOut,
    SloTarget,
)

log = structlog.get_logger(__name__)
router = APIRouter(tags=["case-files"])

Slug = Annotated[str, PathParam(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]

#: The panels a recording can feed; the terminal and the war room need a live system.
RECORDED_TOOLS = ("overview", "logs", "database", "cache", "code", "deploys")
REVIEW_BUSY = "Write-up reviews are unavailable right now. Your answers are saved."


@lru_cache(maxsize=256)
def _package(content_root: Path, slug: str) -> tuple[CaseFileSpec, CaseEvidence] | None:
    """The case file's two halves, or None if the scenario doesn't have both."""
    try:
        folder = find_scenario(content_root, slug)
        return load_case_spec(folder), load_evidence(folder)
    except ContentError:
        return None


def _summary(row: repo.CaseRow, score: int | None) -> CaseFileSummary:
    return CaseFileSummary(
        slug=row.scenario.slug,
        title=row.scenario.title,
        summary=row.scenario.summary,
        track_slug=row.track_slug,
        track_title=row.track_title,
        difficulty=row.scenario.difficulty,
        page=PageOut(severity=row.spec.page.severity, title=row.spec.page.title)
        if row.spec.page
        else None,
        score=score,
    )


def _clues(spec: CaseFileSpec) -> list[CaseClueOut]:
    return [CaseClueOut(panel=c.panel, note=c.note) for c in spec.clues]


def _result(
    spec: CaseFileSpec,
    choices: Mapping[str, str],
    play: CaseFilePlay | None,
    review: Literal["available", "sign_in", "off", "done"],
) -> CaseResultOut:
    scored = casefile.score(spec, choices)
    return CaseResultOut(
        score=scored.score,
        answers=[
            CaseAnswerOut(
                key=a.key,
                choice=a.choice,
                correct=a.correct,
                answer=a.answer,
                explanation_md=a.explanation,
            )
            for a in scored.answers
        ],
        clues=_clues(spec),
        review=review,
        write_up=play.write_up if play else None,
        review_note=play.review_note if play else None,
    )


def _review_state(
    request: Request, play: CaseFilePlay | None, limits: policy.PlanLimits | None
) -> Literal["available", "sign_in", "off", "done"]:
    if limits is None:
        return "sign_in"
    if play is not None and play.reviewed_at is not None:
        return "done"
    if limits.postmortem_reviews == 0 or not llm_of(request.app.state).enabled("case_review"):
        return "off"
    return "available"


async def _found(
    session: SessionDep, content_root: Path, slug: str
) -> tuple[repo.CaseRow, CaseFileSpec, CaseEvidence]:
    row = await repo.published_one(session, slug)
    package = _package(content_root, slug) if row is not None else None
    if row is None or package is None:
        raise AppError(404, "case_file_not_found", "There's no such case file.")
    return row, *package


def _beats(spec: ScenarioSpec) -> list[CaseBeatOut]:
    return [
        CaseBeatOut(at_s=b.at_seconds, persona=b.persona, say=b.say) for b in spec.beats if b.at
    ]


@router.get("/case-files", response_model=CaseFileList)
async def list_case_files(
    session: SessionDep, settings: SettingsDep, user: OptionalUser
) -> CaseFileList:
    """Every case file, free for everyone, with the caller's score on those they've answered."""
    rows = await repo.published(session)
    scores = await repo.scores(session, user.id) if user is not None else {}
    return CaseFileList(
        items=[
            _summary(row, scores.get(row.scenario.id))
            for row in rows
            if _package(settings.content_root, row.scenario.slug) is not None
        ]
    )


@router.get("/case-files/{slug}", response_model=CaseFileOut)
async def get_case_file(
    slug: Slug,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: OptionalUser,
    response: Response,
) -> CaseFileOut:
    """Everything but the recording. A signed-in player who has answered gets their result."""
    response.headers["Cache-Control"] = "no-store"
    row, spec, evidence = await _found(session, settings.content_root, slug)
    play = await repo.play(session, user.id, row.scenario.id) if user is not None else None
    result = None
    if user is not None and play is not None:
        _, limits = await _tier_and_limits(session, _owner(user, None))
        result = _result(spec, play.choices, play, _review_state(request, play, limits))
    unlocked = set(row.spec.unlocked_tools)
    tools = [
        t
        for t in RECORDED_TOOLS
        if t in unlocked
        and not (t == "database" and evidence.db is None)
        and not (t == "cache" and evidence.cache is None)
    ]
    slo = row.spec.slo.targets() if row.spec.slo else {}
    return CaseFileOut(
        **_summary(row, result.score if result else None).model_dump(),
        story=row.spec.briefing.story,
        tools=tools,
        # As in a live incident: the scenario's charts, else the base app's own order.
        metrics=list(row.spec.charts)
        or list(_bundle(settings.content_root, slug).base_app.metrics),
        slo={k: SloTarget(lt=v.lt, gt=v.gt) for k, v in slo.items()},
        deployable=sorted(evidence.deploys),
        host=row.spec.base_app,
        duration_s=evidence.duration_s,
        breached_after_s=evidence.breached_after_s,
        beats=_beats(row.spec),
        questions=[
            CaseQuestionOut(
                key=key,
                prompt=casefile.PROMPTS[key],
                options=[
                    CaseOptionOut(key=o.key, text=o.text)
                    for o in casefile.shuffled(slug, key, casefile.question(spec, key).options)
                ],
            )
            for key in casefile.QUESTION_KEYS
        ],
        result=result,
    )


@router.get(
    "/case-files/{slug}/evidence",
    response_class=Response,
    responses={200: {"model": CaseEvidenceOut, "content": {"application/json": {}}}},
)
async def get_case_evidence(slug: Slug, session: SessionDep, settings: SettingsDep) -> Response:
    """The recording: the same panels as a live incident, as one document. It's a few hundred
    KB and never changes for a given recording, so it's sent as stored, not re-serialised."""
    row, _, evidence = await _found(session, settings.content_root, slug)
    path = evidence_path(find_scenario(settings.content_root, row.scenario.slug))
    return Response(
        content=path.read_bytes(),
        media_type="application/json",
        headers={
            "Cache-Control": "public, max-age=300",
            "ETag": f'"{evidence.source_hash[:16]}-{int(evidence.recorded_at)}"',
        },
    )


@router.post(
    "/case-files/{slug}/answers",
    response_model=CaseResultOut,
    dependencies=[Depends(rate_limit("case-answer", limit=60, window_s=60))],
)
async def answer_case_file(
    slug: Slug,
    body: CaseAnswersIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: OptionalUser,
) -> CaseResultOut:
    """Score the three answers and explain them. A signed-in player's first answers are kept
    (and returned from then on), and answering counts as the day's activity."""
    row, spec, _ = await _found(session, settings.content_root, slug)
    choices: dict[str, str] = {k: getattr(body, k) for k in casefile.QUESTION_KEYS}
    for key, choice in choices.items():
        if choice not in {
            o.key for o in casefile.question(spec, cast(casefile.QuestionKey, key)).options
        }:
            raise AppError(400, "unknown_option", "That isn't one of the options.")
    if user is None:
        return _result(spec, choices, None, "sign_in")
    tz = str(user.profile.prefs.get("timezone") or DEFAULT_TIMEZONE)
    await progress.record_activity(
        session, user.id, activity_day(datetime.now(UTC), tz), "casefile"
    )
    play = await repo.keep_first(
        session,
        user.id,
        row.scenario.id,
        choices=choices,
        score=casefile.score(spec, choices).score,
    )
    _, limits = await _tier_and_limits(session, _owner(user, None))
    return _result(spec, play.choices, play, _review_state(request, play, limits))


@router.post(
    "/case-files/{slug}/review",
    response_model=CaseReviewOut,
    dependencies=[Depends(rate_limit("case-review", limit=10, window_s=3600))],
)
async def review_case_file(
    slug: Slug,
    body: CaseReviewIn,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    user: User,
) -> CaseReviewOut:
    """An AI read of the optional write-up, once per case file, within the plan's allowance
    for write-up reviews (it counts with postmortem reviews)."""
    row, spec, _ = await _found(session, settings.content_root, slug)
    play = await repo.play(session, user.id, row.scenario.id)
    if play is None:
        raise AppError(409, "answer_first", "Answer the three questions first.")
    if play.reviewed_at is not None:
        raise AppError(409, "already_reviewed", "This write-up has been reviewed.")
    _, limits = await _tier_and_limits(session, _owner(user, None))
    if limits.postmortem_reviews == 0:
        raise AppError(403, "reviews_not_in_plan", "Write-up reviews aren't part of your plan.")
    since = policy.period_start(datetime.now(UTC), limits.postmortem_reviews_period)
    if await repo.reviews_used(session, user.id, since) >= limits.postmortem_reviews:
        period = {"day": "today", "week": "this week"}.get(limits.postmortem_reviews_period, "")
        raise AppError(
            429, "ai_allowance", f"You've used your {limits.postmortem_reviews} reviews {period}."
        )
    llm = llm_of(request.app.state)
    if not llm.enabled("case_review"):
        raise AppError(503, "ai_unavailable", REVIEW_BUSY)
    play_id: uuid.UUID = play.id
    write_up = body.write_up.strip()
    title = row.scenario.title
    root_cause = row.spec.ai.root_cause or spec.root_cause.explanation
    await session.commit()  # release the connection for the model call
    try:
        note = await coaching.case_review(
            llm,
            title=title,
            root_cause=root_cause,
            fix=spec.fix.explanation,
            write_up=write_up,
            meta=CallMeta("case_review", user.id),
        )
    except AiUnavailable as exc:
        log.info("case_files.review_unavailable", slug=slug, reason=exc.reason)
        raise AppError(503, "ai_unavailable", REVIEW_BUSY) from exc
    await repo.save_review(session, play_id, write_up, note)
    return CaseReviewOut(write_up=write_up, note=note)
