"""The content console's API (devgrill.domain.admin has who may do what).

Authors, reviewers and admins see the scenarios, their reports and analytics; authors submit
drafts for review; reviewers send back, publish, retire and review unrecognised fixes (ADR 016);
admins also see AI spend, look up users, change roles and read the audit log. Every change is
written to the audit log in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import Date, cast, func, or_, select

from devgrill.ai.classify import groups
from devgrill.domain import admin as policy
from devgrill.domain.enums import AttemptState, Role, ScenarioStatus
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.llm import day_start
from devgrill.infra.models import (
    ActivityDay,
    ApproachCandidate,
    Attempt,
    Entitlement,
    LlmCall,
    Profile,
    Scenario,
    ScenarioVersion,
    Track,
)
from devgrill.infra.repositories import audit
from devgrill_api import pagination
from devgrill_api.deps import Admin, Console, Reviewer, SessionDep, SettingsDep, UserManager
from devgrill_api.errors import AppError
from devgrill_api.schemas import (
    AdminMe,
    AdminScenario,
    AdminScenarioPage,
    AdminUser,
    AiCostsOut,
    AiDayOut,
    AiFeatureCostOut,
    ApproachCandidateGroupOut,
    ApproachCandidateIn,
    ApproachCandidateOut,
    AuditEntry,
    LifecycleIn,
    RolesIn,
    ScenarioAnalytics,
    ValidationReportOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/scenarios", response_model=AdminScenarioPage)
async def admin_scenarios(
    user: Console,
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
            current.c.validation_report["ok"].as_boolean(),
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
                actions=[a.value for a in policy.actions_for(user.roles, s.status)],
                report_ok=report_ok,
            )
            for s, track_slug, version, report_ok, attempts, resolved in page
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
    _: Reviewer, session: SessionDep
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
    candidate_id: uuid.UUID, body: ApproachCandidateIn, user: Reviewer, session: SessionDep
) -> Response:
    """Mark a candidate promoted (an author writes it up as an approach) or dismissed."""
    candidate = await session.get(ApproachCandidate, candidate_id, with_for_update=True)
    if candidate is None:
        raise AppError(404, "not_found", "No such candidate.")
    candidate.status = body.status
    await audit.record(
        session, user.id, f"approach_candidate.{body.status}", f"candidate:{candidate_id}"
    )
    await session.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- the console


@router.get("/me", response_model=AdminMe)
async def admin_me(user: Console) -> AdminMe:
    """The caller's roles and what they allow, so the console shows only what works."""
    return AdminMe(
        roles=sorted(user.roles),
        permissions=sorted(p.value for p in policy.Permission if policy.allowed(user.roles, p)),
    )


def _report_ok(version: ScenarioVersion | None) -> bool | None:
    if version is None or not version.validation_report:
        return None
    return bool(version.validation_report.get("ok"))


@router.post("/scenarios/{slug}/actions/{action}", response_model=AdminScenario)
async def admin_scenario_action(
    slug: pagination.SlugPath,
    action: policy.Action,
    body: LifecycleIn,
    user: Console,
    session: SessionDep,
) -> AdminScenario:
    """Move a scenario through its lifecycle (draft, review, published, retired)."""
    rule = policy.TRANSITIONS[action]
    if not policy.allowed(user.roles, rule.needs):
        raise AppError(403, "forbidden", "Your role can't do that to a scenario.")
    scenario = (
        await session.execute(select(Scenario).where(Scenario.slug == slug).with_for_update())
    ).scalar_one_or_none()
    if scenario is None:
        raise AppError(404, "not_found", f"No scenario called {slug!r}.")
    if scenario.status is not rule.source:
        raise AppError(
            409,
            "invalid_transition",
            f"It's {scenario.status.value}. That needs a {rule.source.value} scenario.",
        )
    if action is policy.Action.SEND_BACK and not (body.note and body.note.strip()):
        raise AppError(400, "note_required", "Say what needs changing when you send it back.")
    before = scenario.status
    scenario.status = rule.target
    version = (
        await session.get(ScenarioVersion, scenario.current_version_id)
        if scenario.current_version_id
        else None
    )
    if rule.target is ScenarioStatus.PUBLISHED and version and version.published_at is None:
        version.published_at = datetime.now(UTC)
    await audit.record(
        session,
        user.id,
        f"scenario.{action.value}",
        f"scenario:{slug}",
        {"from": before.value, "to": rule.target.value, "note": body.note},
    )
    await session.commit()
    await session.refresh(scenario)
    if version is not None:
        await session.refresh(version)
    track_slug = await session.scalar(select(Track.slug).where(Track.id == scenario.track_id))
    return AdminScenario(
        slug=scenario.slug,
        title=scenario.title,
        track_slug=track_slug or "",
        difficulty=scenario.difficulty,
        status=scenario.status,
        version=version.version if version else None,
        attempts=0,
        resolved=0,
        updated_at=scenario.updated_at,
        actions=[a.value for a in policy.actions_for(user.roles, scenario.status)],
        report_ok=_report_ok(version),
    )


@router.get("/scenarios/{slug}/report", response_model=ValidationReportOut)
async def admin_scenario_report(
    slug: pagination.SlugPath, _: Console, session: SessionDep
) -> ValidationReportOut:
    """The current version's validation report (`devgrill-content test`, attached at seed)."""
    row = (
        await session.execute(
            select(ScenarioVersion.version, ScenarioVersion.validation_report)
            .join(Scenario, Scenario.current_version_id == ScenarioVersion.id)
            .where(Scenario.slug == slug)
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "not_found", f"No scenario called {slug!r}.")
    return ValidationReportOut(slug=slug, version=row[0], report=row[1])


FINISHED = (
    AttemptState.RESOLVED,
    AttemptState.ABANDONED,
    AttemptState.EXPIRED,
    AttemptState.FAILED,
)
LEFT = (AttemptState.ABANDONED, AttemptState.EXPIRED)


@router.get("/analytics/scenarios", response_model=list[ScenarioAnalytics])
async def admin_analytics(_: Console, session: SessionDep) -> list[ScenarioAnalytics]:
    """Per scenario (all versions): solve rate, median time, hints, drop-off, rating drift,
    with automatic flags (devgrill.domain.admin.flags)."""
    took = Attempt.resolved_at - func.coalesce(Attempt.active_at, Attempt.started_at)
    minutes = func.extract("epoch", took) / 60
    resolved = Attempt.state == AttemptState.RESOLVED
    stats = (
        select(
            ScenarioVersion.scenario_id.label("scenario_id"),
            func.count(Attempt.id).label("n"),
            func.count(Attempt.id).filter(resolved).label("solved"),
            func.count(Attempt.id).filter(Attempt.state.in_(LEFT)).label("left"),
            func.percentile_cont(0.5).within_group(minutes).filter(resolved).label("median"),
            func.avg(Attempt.hints_used).label("hints"),
        )
        .join(Attempt, Attempt.scenario_version_id == ScenarioVersion.id)
        .where(Attempt.state.in_(FINISHED))
        .group_by(ScenarioVersion.scenario_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Scenario, stats.c.n, stats.c.solved, stats.c.left, stats.c.median, stats.c.hints)
            .outerjoin(stats, stats.c.scenario_id == Scenario.id)
            .order_by(Scenario.slug)
        )
    ).all()
    out: list[ScenarioAnalytics] = []
    for s, n, solved, left, median, hints in rows:
        count = int(n or 0)
        solve_rate = (solved or 0) / count if count else 0.0
        abandon_rate = (left or 0) / count if count else 0.0
        median_minutes = round(float(median), 1) if median is not None else None
        hints_per = round(float(hints or 0), 2)
        out.append(
            ScenarioAnalytics(
                slug=s.slug,
                title=s.title,
                status=s.status,
                est_minutes=s.est_minutes,
                attempts=count,
                solve_rate=round(solve_rate, 3),
                abandon_rate=round(abandon_rate, 3),
                median_minutes=median_minutes,
                hints_per_attempt=hints_per,
                rating_drift=round(s.rating - 1500.0, 1),
                flags=policy.flags(
                    attempts=count,
                    solve_rate=solve_rate,
                    abandon_rate=abandon_rate,
                    median_minutes=median_minutes,
                    est_minutes=s.est_minutes,
                    hints_per_attempt=hints_per,
                ),
            )
        )
    return out


@router.get("/users", response_model=list[AdminUser])
async def admin_users(
    _: UserManager,
    session: SessionDep,
    q: Annotated[str, Query(min_length=2, max_length=40, pattern=r"^[^\x00-\x1f\x7f]+$")],
) -> list[AdminUser]:
    """Support lookup by handle or display name (prefix, case-insensitive), at most 20."""
    escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    attempts = select(Attempt.user_id, func.count().label("n")).group_by(Attempt.user_id).subquery()
    last = (
        select(ActivityDay.user_id, func.max(ActivityDay.day).label("day"))
        .group_by(ActivityDay.user_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Profile, Entitlement.plan, attempts.c.n, last.c.day)
            .outerjoin(Entitlement, Entitlement.user_id == Profile.user_id)
            .outerjoin(attempts, attempts.c.user_id == Profile.user_id)
            .outerjoin(last, last.c.user_id == Profile.user_id)
            .where(
                or_(
                    Profile.handle.ilike(f"{escaped}%"),
                    Profile.display_name.ilike(f"{escaped}%"),
                )
            )
            .order_by(Profile.handle)
            .limit(20)
        )
    ).all()
    return [
        AdminUser(
            user_id=p.user_id,
            handle=p.handle,
            display_name=p.display_name,
            roles=p.roles,
            plan=str(plan or "free"),
            attempts=int(n or 0),
            last_active=day,
            created_at=p.created_at,
        )
        for p, plan, n, day in rows
    ]


@router.put("/users/{user_id}/roles", response_model=AdminUser)
async def admin_set_roles(
    user_id: uuid.UUID, body: RolesIn, user: UserManager, session: SessionDep
) -> AdminUser:
    """Set a user's roles ("user" is always kept). Admins can't remove their own admin role."""
    profile = await session.get(Profile, user_id, with_for_update=True)
    if profile is None:
        raise AppError(404, "not_found", "No such user.")
    roles = sorted({Role.USER.value, *(r.value for r in body.roles)})
    if user_id == user.id and Role.ADMIN.value not in roles:
        raise AppError(400, "own_admin", "You can't remove your own admin role.")
    before = list(profile.roles)
    profile.roles = roles
    await audit.record(
        session, user.id, "user.roles", f"user:{profile.handle}", {"from": before, "to": roles}
    )
    await session.commit()
    return AdminUser(
        user_id=profile.user_id,
        handle=profile.handle,
        display_name=profile.display_name,
        roles=profile.roles,
        plan="free",
        attempts=0,
        last_active=None,
        created_at=profile.created_at,
    )


@router.get("/audit", response_model=list[AuditEntry])
async def admin_audit(
    _: Admin,
    session: SessionDep,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: pagination.Limit = 50,
) -> list[AuditEntry]:
    """The audit log, newest first (keyset on id)."""
    return [
        AuditEntry(id=e.id, ts=e.ts, actor=handle, action=e.action, target=e.target, data=e.data)
        for e, handle in await audit.recent(session, limit=limit, before_id=before)
    ]
