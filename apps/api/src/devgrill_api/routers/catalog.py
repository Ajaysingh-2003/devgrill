"""Catalog: tracks, scenarios, briefings, approaches and challenges (public, cacheable)."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Response
from pydantic import ValidationError

from devgrill.domain.enums import Access, AttemptMode, ChallengeKind, Difficulty
from devgrill.domain.spec import BriefingSpec, Goal
from devgrill.infra.models import ScenarioVersion
from devgrill.infra.repositories import catalog, challenges
from devgrill.infra.repositories.catalog import ScenarioRow, TrackRow
from devgrill_api import pagination
from devgrill_api.deps import OptionalUser, SessionDep, User
from devgrill_api.errors import AppError
from devgrill_api.schemas import (
    ApproachOut,
    Briefing,
    ChallengeOut,
    ScenarioCard,
    ScenarioPage,
    ScenarioProgress,
    ScenarioStats,
    TopicOut,
    TrackDetail,
    TrackProgress,
    TrackSummary,
)

router = APIRouter(tags=["catalog"])

#: Solve rate is hidden until this many attempts have ended (small samples mislead).
MIN_ENDED_FOR_SOLVE_RATE = 10
#: Modes a briefing offers until scenarios declare their own (phase 3).
DEFAULT_MODES = [AttemptMode.GUIDED, AttemptMode.ONCALL]
DEFAULT_GOALS = [
    Goal(
        title="Get it working",
        detail="Get customers back to working pages as fast as you safely can.",
    ),
    Goal(title="Find the root cause", detail="Not just what is slow, but why it started now."),
    Goal(
        title="Fix it properly",
        detail="When you check your fix, we replay the traffic and test the weak spots.",
    ),
    Goal(title="Write it up", detail="Your teammates want to know what happened and why."),
]

# Anonymous catalog responses can be cached by browsers and CDNs; personalised ones can't.
_PUBLIC_CACHE = "public, max-age=60, stale-while-revalidate=300"
_PRIVATE = "private, no-store"


def _cache(response: Response, user: object | None) -> None:
    response.headers["Cache-Control"] = _PRIVATE if user is not None else _PUBLIC_CACHE
    response.headers["Vary"] = "Authorization"


def card(row: ScenarioRow, progress: str | None = None) -> ScenarioCard:
    s = row.scenario
    return ScenarioCard(
        slug=s.slug,
        title=s.title,
        summary=s.summary,
        difficulty=s.difficulty,
        est_minutes=s.est_minutes,
        tags=s.tags,
        track_slug=row.track_slug,
        topic_slug=row.topic.slug if row.topic else None,
        topic_title=row.topic.title if row.topic else None,
        access=Access(s.access),
        playable=row.playable,
        progress=cast(ScenarioProgress | None, progress),
    )


def _summary(
    row: TrackRow, progress: catalog.Progress | None, rating: float | None, signed_in: bool
) -> dict[str, object]:
    t = row.track
    mine = None
    if signed_in:
        solved = progress.solved if progress else 0
        mine = TrackProgress(
            solved=solved,
            attempted=progress.attempted if progress else 0,
            mastery_pct=round(100 * solved / row.scenario_count) if row.scenario_count else 0,
            rating=rating,
        )
    return {
        "slug": t.slug,
        "title": t.title,
        "summary": t.summary,
        "icon": t.icon,
        "position": t.position,
        "scenario_count": row.scenario_count,
        "topics": [topic.title for topic in row.topics],
        "progress": mine,
    }


@router.get("/tracks", response_model=list[TrackSummary])
async def list_tracks(
    session: SessionDep, user: OptionalUser, response: Response
) -> list[TrackSummary]:
    """Published tracks with scenario counts, plus the caller's progress when signed in."""
    rows = await catalog.published_tracks(session)
    progress = await catalog.track_progress(session, user.id) if user else {}
    ratings = await catalog.ratings(session, user.id) if user else {}
    _cache(response, user)
    return [
        TrackSummary.model_validate(
            _summary(
                r,
                progress.get(r.track.id),
                ratings[r.track.id].rating if r.track.id in ratings else None,
                user is not None,
            )
        )
        for r in rows
    ]


@router.get("/tracks/{slug}", response_model=TrackDetail)
async def get_track(
    slug: pagination.SlugPath, session: SessionDep, user: OptionalUser, response: Response
) -> TrackDetail:
    """A track's topics and every published scenario in it, easiest first."""
    row = await catalog.track_by_slug(session, slug)
    if row is None:
        raise AppError(404, "track_not_found", f"No track called {slug!r}.")
    scenario_rows = await catalog.scenarios(session, track_slug=slug, order_by_difficulty=True)
    states = (
        await catalog.scenario_progress(session, user.id, [r.scenario.id for r in scenario_rows])
        if user
        else {}
    )
    progress = (await catalog.track_progress(session, user.id)).get(row.track.id) if user else None
    rating = (await catalog.ratings(session, user.id)).get(row.track.id) if user else None

    by_topic: dict[str | None, list[ScenarioCard]] = {}
    for r in scenario_rows:
        default = "new" if user else None
        by_topic.setdefault(r.topic.slug if r.topic else None, []).append(
            card(r, states.get(r.scenario.id, default))
        )
    topics = [
        TopicOut(
            slug=t.slug,
            title=t.title,
            has_primer=bool(t.primer_md),
            primer_md=t.primer_md,
            scenarios=by_topic.get(t.slug, []),
        )
        for t in row.topics
    ]
    if by_topic.get(None):
        topics.append(
            TopicOut(slug="other", title="Other", has_primer=False, scenarios=by_topic[None])
        )
    _cache(response, user)
    return TrackDetail.model_validate(
        {
            **_summary(row, progress, rating.rating if rating else None, user is not None),
            "topics_detail": topics,
        }
    )


@router.get("/scenarios", response_model=ScenarioPage)
async def list_scenarios(
    session: SessionDep,
    user: OptionalUser,
    response: Response,
    track: pagination.SlugQuery = None,
    topic: pagination.SlugQuery = None,
    difficulty: Difficulty | None = None,
    q: pagination.SearchQuery = None,
    cursor: pagination.Cursor = None,
    limit: pagination.Limit = 20,
) -> ScenarioPage:
    """Published scenarios, filterable, ordered by slug with cursor pagination."""
    after = pagination.decode(cursor) if cursor else None
    if after is not None and not isinstance(after, str):
        raise AppError(400, "invalid_cursor", "The cursor is not valid.")
    rows = await catalog.scenarios(
        session,
        track_slug=track,
        topic_slug=topic,
        difficulty=difficulty,
        query=q,
        after_slug=after,
        limit=limit + 1,
    )
    page, more = rows[:limit], len(rows) > limit
    states = (
        await catalog.scenario_progress(session, user.id, [r.scenario.id for r in page])
        if user
        else {}
    )
    _cache(response, user)
    return ScenarioPage(
        items=[card(r, states.get(r.scenario.id, "new") if user else None) for r in page],
        next_cursor=pagination.encode(page[-1].scenario.slug) if more and page else None,
    )


@router.get("/scenarios/{slug}", response_model=Briefing)
async def get_scenario(
    slug: pagination.SlugPath, session: SessionDep, user: OptionalUser, response: Response
) -> Briefing:
    """The briefing: story, system, goals and stats. Never contains solution data."""
    found = await catalog.scenario_by_slug(session, slug)
    if found is None:
        raise AppError(404, "scenario_not_found", f"No scenario called {slug!r}.")
    row, track, version = found
    try:
        spec = BriefingSpec.model_validate(version.spec.get("briefing", {}))
    except ValidationError as exc:
        raise AppError(
            500, "invalid_scenario_spec", "This scenario's briefing is malformed."
        ) from exc
    if not spec.goals:
        spec = spec.model_copy(update={"goals": DEFAULT_GOALS})

    stats = await catalog.stats(session, row.scenario.id)
    solve_rate = (
        round(100 * stats.resolved / stats.ended)
        if stats.ended >= MIN_ENDED_FOR_SOLVE_RATE
        else None
    )
    progress = None
    if user:
        progress = (await catalog.scenario_progress(session, user.id, [row.scenario.id])).get(
            row.scenario.id, "new"
        )
    warm = await catalog.warmup(session, row.scenario)
    _cache(response, user)
    return Briefing.model_validate(
        {
            **card(row, progress).model_dump(),
            "version": version.version,
            "track_title": track.title,
            "briefing": spec,
            "stats": ScenarioStats(
                players=stats.players,
                solve_rate_pct=solve_rate,
                median_minutes=round(stats.median_minutes) if stats.median_minutes else None,
            ),
            "modes": DEFAULT_MODES,
            "warmup": card(warm) if warm else None,
        }
    )


@router.get("/scenarios/{slug}/approaches", response_model=list[ApproachOut])
async def get_approaches(
    slug: pagination.SlugPath, session: SessionDep, user: User
) -> list[ApproachOut]:
    """Known fixes. Spoilers, so only for players who have resolved the scenario (else 403)."""
    found = await catalog.scenario_by_slug(session, slug)
    if found is None:
        raise AppError(404, "scenario_not_found", f"No scenario called {slug!r}.")
    row, _, _ = found
    if not await catalog.has_resolved(session, user.id, row.scenario.id):
        raise AppError(403, "not_resolved", "Fix this drill to see the other ways to fix it.")
    return [
        ApproachOut.model_validate(a) for a in await catalog.approaches(session, row.scenario.id)
    ]


async def _challenge(kind: ChallengeKind, session: SessionDep) -> ChallengeOut:
    found = await challenges.current(session, kind)
    if found is None:
        raise AppError(404, "no_challenge", "There is no challenge right now.")
    challenge, players = found
    version = await session.get(ScenarioVersion, challenge.scenario_version_id)
    scenario_row = await catalog.scenario_row(session, version.scenario_id) if version else None
    if scenario_row is None:
        raise AppError(404, "no_challenge", "This challenge's scenario is no longer available.")
    return ChallengeOut(
        kind=kind,
        starts_at=challenge.starts_at,
        ends_at=challenge.ends_at,
        scenario=card(scenario_row),
        players=players,
    )


@router.get("/challenges/daily", response_model=ChallengeOut)
async def daily_challenge(session: SessionDep) -> ChallengeOut:
    """Today's incident (IST day), the same for everyone."""
    return await _challenge(ChallengeKind.DAILY, session)


@router.get("/challenges/weekly", response_model=ChallengeOut)
async def weekly_challenge(session: SessionDep) -> ChallengeOut:
    """This week's incident (from Monday 00:00 IST)."""
    return await _challenge(ChallengeKind.WEEKLY, session)
