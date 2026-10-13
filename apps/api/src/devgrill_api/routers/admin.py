"""Admin read endpoints (role: admin). Writes (validate, publish, review) arrive in phase 3."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from devgrill.domain.enums import AttemptState, ScenarioStatus
from devgrill.infra.models import Attempt, Scenario, ScenarioVersion, Track
from devgrill_api import pagination
from devgrill_api.deps import Admin, SessionDep
from devgrill_api.errors import AppError
from devgrill_api.schemas import AdminScenario, AdminScenarioPage

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
