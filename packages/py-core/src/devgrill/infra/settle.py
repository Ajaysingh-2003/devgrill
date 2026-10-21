"""Settling a finished attempt (ADR 015): its score, its approach, ratings, the activity day.

Runs once per attempt, after teardown (the SandboxLifecycle workflow's last step). Idempotent:
an attempt that already has a score is left alone, so retries are safe. One transaction:
the score, the rating rows, their history and the activity day land together or not at all.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain import ratings, scoring
from devgrill.domain.debrief import match_approach
from devgrill.domain.enums import AttemptState, ProbeKind, StreakMode, VerifyStatus
from devgrill.domain.glicko2 import Rating
from devgrill.domain.spec import ApproachMatch, ScenarioSpec
from devgrill.domain.streaks import DEFAULT_TIMEZONE, activity_day
from devgrill.infra.models import (
    ActivityDay,
    Approach,
    Attempt,
    AttemptEvent,
    CodeChange,
    Profile,
    RatingHistory,
    Scenario,
    ScenarioVersion,
    SkillRating,
    VerifyRun,
)
from devgrill.infra.repositories.progress import refresh_streak

#: Probe kinds that measure the SLO from outside (they gate mitigation-time credit).
SLO_KINDS = frozenset({ProbeKind.LOAD.value, ProbeKind.CHAOS.value})


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: uuid.UUID
    resolution: float
    slo_held: bool
    passed: bool


def summarise_run(run: VerifyRun) -> RunSummary | None:
    """Resolution of one finished verify run, from the probe results in its summary."""
    probes = (run.summary or {}).get("probes") or []
    if run.status not in (VerifyStatus.PASSED, VerifyStatus.PARTIAL, VerifyStatus.FAILED):
        return None
    total = sum(float(p.get("weight", 1.0)) for p in probes)
    passed = sum(float(p.get("weight", 1.0)) for p in probes if p.get("passed"))
    slo = [p for p in probes if p.get("kind") in SLO_KINDS]
    return RunSummary(
        run_id=run.id,
        resolution=round(passed / total, 4) if total else 0.0,
        slo_held=bool(slo) and all(p.get("passed") for p in slo),
        passed=run.status is VerifyStatus.PASSED,
    )


async def settle(
    session: AsyncSession,
    attempt_id: uuid.UUID,
    *,
    approach_rules: list[tuple[str, ApproachMatch | None]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Score and rate a finished attempt. Returns the stored score, or None if not settled."""
    attempt = await session.get(Attempt, attempt_id, with_for_update=True)
    if attempt is None or attempt.score is not None:
        return attempt.score if attempt is not None else None
    if attempt.state not in (
        AttemptState.RESOLVED,
        AttemptState.EXPIRED,
        AttemptState.ABANDONED,
        AttemptState.FAILED,
    ):
        return None  # still live: settled when it ends
    stamp = now or datetime.now(UTC)
    version = await session.get(ScenarioVersion, attempt.scenario_version_id)
    assert version is not None
    spec = ScenarioSpec.model_validate(version.spec)
    scenario = await session.get(Scenario, version.scenario_id, with_for_update=True)
    assert scenario is not None

    runs = list(
        (
            await session.scalars(
                select(VerifyRun)
                .where(VerifyRun.attempt_id == attempt_id)
                .order_by(VerifyRun.created_at)
            )
        ).all()
    )
    summaries = [s for r in runs if (s := summarise_run(r)) is not None]
    best = max(summaries, key=lambda s: (s.passed, s.resolution), default=None)
    messages = await session.scalar(
        select(func.count())
        .select_from(AttemptEvent)
        .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == "message")
    )
    mitigation_minutes = (
        (attempt.mitigated_at - attempt.active_at).total_seconds() / 60
        if attempt.mitigated_at and attempt.active_at
        else None
    )
    w = spec.scoring
    result = scoring.score(
        scoring.ScoreInput(
            weights=scoring.Weights(
                mitigation_time=w.mitigation_time,
                resolution=w.resolution,
                postmortem=w.postmortem,
                communication=w.communication,
            ),
            par_minutes=spec.mitigation_par_minutes,
            mitigation_minutes=mitigation_minutes,
            resolution=1.0
            if attempt.state is AttemptState.RESOLVED
            else (best.resolution if best else 0.0),
            slo_held_under_verify=bool(best and best.slo_held),
            hints_used=attempt.hints_used,
            status_updates=int(messages or 0),
        )
    )
    attempt.score = {
        **asdict(result),
        "par_minutes": spec.mitigation_par_minutes,
        "mitigation_minutes": round(mitigation_minutes, 2) if mitigation_minutes else None,
        "verify_runs": len(summaries),
        "best_run_id": str(best.run_id) if best else None,
        "status_updates": int(messages or 0),
        "hints_used": attempt.hints_used,
        "weights": spec.scoring.model_dump(),
    }

    # The approach, by the scenario's rules (the AI takes over in phase 6).
    if approach_rules:
        diffs = list(
            (
                await session.scalars(
                    select(CodeChange.diff).where(
                        CodeChange.attempt_id == attempt_id, CodeChange.deploy_ok.is_(True)
                    )
                )
            ).all()
        )
        rolled_back = bool(
            await session.scalar(
                select(AttemptEvent.id)
                .where(
                    AttemptEvent.attempt_id == attempt_id,
                    AttemptEvent.type == "rollback",
                    AttemptEvent.payload["ok"].as_boolean().is_(True),
                )
                .limit(1)
            )
        )
        key = match_approach(approach_rules, rolled_back=rolled_back, diffs=diffs)
        if key is not None:
            attempt.approach_id = await session.scalar(
                select(Approach.id).where(Approach.scenario_id == scenario.id, Approach.key == key)
            )
            attempt.approach_confidence = 1.0 if attempt.approach_id else None

    # Ratings.
    active_seconds = (
        ((attempt.ended_at or stamp) - attempt.active_at).total_seconds()
        if attempt.active_at
        else 0.0
    )
    if attempt.user_id is not None and ratings.rated(
        signed_in=True,
        mode=attempt.mode,
        state=attempt.state,
        active_seconds=active_seconds,
        verify_runs=len(summaries),
    ):
        await _rate(session, attempt, scenario, result.incident)

    # Streaks count days with a finished incident.
    if attempt.user_id is not None and attempt.state is not AttemptState.FAILED:
        profile = await session.get(Profile, attempt.user_id)
        prefs = profile.prefs if profile else {}
        tz = str(prefs.get("timezone") or DEFAULT_TIMEZONE)
        day = activity_day(stamp, tz)
        stmt = insert(ActivityDay).values(user_id=attempt.user_id, day=day, kinds=["incident"])
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["user_id", "day"],
                set_={
                    "kinds": case(
                        (ActivityDay.kinds.contains(["incident"]), ActivityDay.kinds),
                        else_=func.array_append(ActivityDay.kinds, "incident"),
                    )
                },
            )
        )
        await refresh_streak(
            session,
            attempt.user_id,
            today=day,
            mode=StreakMode(str(prefs.get("streak_mode") or StreakMode.DAILY.value)),
        )
    await session.flush()
    return attempt.score


async def _rate(
    session: AsyncSession, attempt: Attempt, scenario: Scenario, outcome: float
) -> None:
    assert attempt.user_id is not None
    track_id = scenario.track_id
    await session.execute(
        insert(SkillRating)
        .values(user_id=attempt.user_id, track_id=track_id)
        .on_conflict_do_nothing(index_elements=["user_id", "track_id"])
    )
    row = await session.scalar(
        select(SkillRating)
        .where(SkillRating.user_id == attempt.user_id, SkillRating.track_id == track_id)
        .with_for_update()
    )
    assert row is not None
    player = Rating(row.rating, row.rd, row.vol)
    opponent = Rating(scenario.rating, scenario.rd, scenario.vol)
    change = ratings.rate_attempt(player, opponent, outcome, attempt.mode)
    row.rating, row.rd, row.vol = (
        change.player_after.rating,
        change.player_after.rd,
        change.player_after.vol,
    )
    row.games += 1
    scenario.rating, scenario.rd, scenario.vol = (
        change.scenario_after.rating,
        change.scenario_after.rd,
        change.scenario_after.vol,
    )
    session.add(
        RatingHistory(
            user_id=attempt.user_id,
            track_id=track_id,
            attempt_id=attempt.id,
            before=ratings.as_dict(change.player_before),
            after=ratings.as_dict(change.player_after),
        )
    )
    attempt.rating_delta = {
        "track_id": str(track_id),
        "before": ratings.as_dict(change.player_before),
        "after": ratings.as_dict(change.player_after),
        "delta": round(change.delta, 1),
        "expected": round(change.expected, 3),
        "outcome": round(outcome, 4),
        "mode": attempt.mode.value,
    }
