"""Admin endpoints (role: admin): the scenario list, AI spend, and the queue of fixes the
classifier didn't recognise (ADR 016)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Response
from sqlalchemy import Date, cast, func, select

from devgrill.ai.classify import groups
from devgrill.domain.enums import AttemptState, ScenarioStatus
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.llm import day_start
from devgrill.infra.models import (
    ApproachCandidate,
    Attempt,
    LlmCall,
    Scenario,
    ScenarioVersion,
    Track,
)
from devgrill_api import pagination
from devgrill_api.deps import Admin, SessionDep, SettingsDep
from devgrill_api.errors import AppError
from devgrill_api.schemas import (
    AdminScenario,
    AdminScenarioPage,
    AiCostsOut,
    AiDayOut,
    AiFeatureCostOut,
    ApproachCandidateGroupOut,
    ApproachCandidateIn,
    ApproachCandidateOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/scenarios", response_model=AdminScenarioPage)
async def admin_scenarios(
    _: Admin,
    session: SessionDep,
    status: ScenarioStatus | None = None,
    track: pagination.SlugQuery = None,
    cursor: pagination.Cursor = None,
    limit: pagination.Limit = 50,
) -> AdminScenarioPage:
    """Every scenario in any status, with attempt counts."""
    after = pagination.decode(cursor) if cursor else None
    if after is not None and not isinstance(after, str):
        raise AppError(400, "invalid_cursor", "The cursor is not valid.")

    counts = (
        select(
            ScenarioVersion.scenario_id,
            func.count(Attempt.id).label("attempts"),
            func.count(Attempt.id).filter(Attempt.state == AttemptState.RESOLVED).label("resolved"),
        )
        .join(Attempt, Attempt.scenario_version_id == ScenarioVersion.id)
        .group_by(ScenarioVersion.scenario_id)
        .subquery()
    )
    current = ScenarioVersion.__table__.alias("current_version")
    stmt = (
        select(
            Scenario,
            Track.slug,
            current.c.version,
            func.coalesce(counts.c.attempts, 0),
            func.coalesce(counts.c.resolved, 0),
        )
        .join(Track, Track.id == Scenario.track_id)
        .outerjoin(current, current.c.id == Scenario.current_version_id)
        .outerjoin(counts, counts.c.scenario_id == Scenario.id)
        .order_by(Scenario.slug)
        .limit(limit + 1)
    )
    if status:
        stmt = stmt.where(Scenario.status == status)
    if track:
        stmt = stmt.where(Track.slug == track)
    if after:
        stmt = stmt.where(Scenario.slug > after)
    rows = (await session.execute(stmt)).all()
    page, more = rows[:limit], len(rows) > limit
    return AdminScenarioPage(
        items=[
            AdminScenario(
                slug=s.slug,
                title=s.title,
                track_slug=track_slug,
                difficulty=s.difficulty,
                status=s.status,
                version=version,
                attempts=int(attempts),
                resolved=int(resolved),
                updated_at=s.updated_at,
            )
            for s, track_slug, version, attempts, resolved in page
        ],
        next_cursor=pagination.encode(page[-1][0].slug) if more and page else None,
    )


# ------------------------------------------------------------------------------- AI


@router.get("/ai/costs", response_model=AiCostsOut)
async def admin_ai_costs(_: Admin, session: SessionDep, settings: SettingsDep) -> AiCostsOut:
    """Model spend from llm_calls (IST days)."""
    now = datetime.now(UTC)
    today = day_start(now)
    spent = await session.scalar(
        select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(LlmCall.created_at >= today)
    )
    local_day = cast(func.timezone(DEFAULT_TIMEZONE, LlmCall.created_at), Date)
    days = (
        await session.execute(
            select(local_day, func.count(), func.coalesce(func.sum(LlmCall.cost_usd), 0))
            .where(LlmCall.created_at >= today - timedelta(days=13))
            .group_by(local_day)
            .order_by(local_day)
        )
    ).all()
    week = today - timedelta(days=6)
    features = (
        await session.execute(
            select(
                LlmCall.feature,
                func.count(),
                func.count().filter(LlmCall.status != "ok"),
                func.coalesce(func.sum(LlmCall.cost_usd), 0),
                func.coalesce(func.sum(LlmCall.input_tokens), 0),
                func.coalesce(func.sum(LlmCall.output_tokens), 0),
                func.percentile_cont(0.95).within_group(LlmCall.latency_ms),
            )
            .where(LlmCall.created_at >= week)
            .group_by(LlmCall.feature)
            .order_by(LlmCall.feature)
        )
    ).all()
    per_attempt = (
        select(func.sum(LlmCall.cost_usd).label("cost"))
        .where(LlmCall.created_at >= week, LlmCall.attempt_id.is_not(None))
        .group_by(LlmCall.attempt_id)
        .subquery()
    )
    average = await session.scalar(select(func.avg(per_attempt.c.cost)))
    return AiCostsOut(
        budget_usd=settings.llm_daily_budget_usd,
        spent_today_usd=float(Decimal(spent or 0)),
        days=[AiDayOut(day=d, calls=int(n), cost_usd=float(c)) for d, n, c in days],
        features=[
            AiFeatureCostOut(
                feature=f,
                calls=int(n),
                errors=int(e),
                cost_usd=float(c),
                input_tokens=int(i),
                output_tokens=int(o),
                p95_latency_ms=round(p) if p is not None else None,
            )
            for f, n, e, c, i, o, p in features
        ],
        per_attempt_usd=round(float(average), 6) if average is not None else None,
    )


@router.get("/approach-candidates", response_model=list[ApproachCandidateGroupOut])
async def admin_approach_candidates(
    _: Admin, session: SessionDep
) -> list[ApproachCandidateGroupOut]:
    """Open candidates, grouped per scenario into clusters of similar fixes (largest first)."""
    rows = (
        await session.execute(
            select(ApproachCandidate, Scenario.slug, Scenario.title)
            .join(Scenario, Scenario.id == ApproachCandidate.scenario_id)
            .where(ApproachCandidate.status == "open")
            .order_by(Scenario.slug, ApproachCandidate.created_at)
            .limit(500)
        )
    ).all()
    by_scenario: dict[str, list[tuple[ApproachCandidate, str]]] = {}
    for candidate, slug, title in rows:
        by_scenario.setdefault(slug, []).append((candidate, title))
    out: list[ApproachCandidateGroupOut] = []
    for slug, items in by_scenario.items():
        with_vector = [c for c, _ in items if c.embedding is not None]
        without = [c for c, _ in items if c.embedding is None]
        clusters = [
            [with_vector[i] for i in group]
            for group in groups([list(c.embedding) for c in with_vector])  # type: ignore[arg-type]
        ] + [[c] for c in without]
        for cluster in clusters:
            out.append(
                ApproachCandidateGroupOut(
                    scenario_slug=slug,
                    scenario_title=items[0][1],
                    candidates=[ApproachCandidateOut.model_validate(c) for c in cluster],
                )
            )
    return sorted(out, key=lambda g: (-len(g.candidates), g.scenario_slug))


@router.post("/approach-candidates/{candidate_id}", status_code=204)
async def admin_review_candidate(
    candidate_id: uuid.UUID, body: ApproachCandidateIn, _: Admin, session: SessionDep
) -> Response:
    """Mark a candidate promoted (an author writes it up as an approach) or dismissed."""
    candidate = await session.get(ApproachCandidate, candidate_id, with_for_update=True)
    if candidate is None:
        raise AppError(404, "not_found", "No such candidate.")
    candidate.status = body.status
    await session.commit()
    return Response(status_code=204)
