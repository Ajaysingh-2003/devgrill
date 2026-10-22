"""The AI features on real attempts (ADR 016): what they read, and the work done afterwards.

Reading: the scenario, the player's trail (the debrief replay's lines, redacted, with event
ids), the war room and the hints taken, for teammates, nudges and the coach.

After the incident (the worker; each step best effort and idempotent):
- `review_attempt`: the coach note, and the approach when the scenario's rules didn't
  recognise it (unknown fixes become candidates for the admin queue). Stored in the score.
- `grade_postmortem`: the judge's grade (a `postmortem_grades` row), which fills the score's
  postmortem component and total. Ratings never move (ADR 015).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devgrill.ai import classify as cls
from devgrill.ai import coaching, grading, teammates
from devgrill.ai.port import AiUnavailable, CallMeta, Llm
from devgrill.ai.registry import prompt
from devgrill.ai.safety import redact
from devgrill.domain import scoring
from devgrill.domain.debrief import REPLAY_TYPES, TrailEvent, replay
from devgrill.domain.enums import AuthorKind
from devgrill.domain.spec import RubricCriterion, ScenarioSpec
from devgrill.infra.models import (
    Approach,
    ApproachCandidate,
    Attempt,
    AttemptEvent,
    CodeChange,
    Postmortem,
    PostmortemGrade,
    Scenario,
    ScenarioVersion,
    VerifyRun,
    WarRoomMessage,
)
from devgrill.infra.models.catalog import EMBEDDING_DIMENSIONS
from devgrill.infra.repositories import attempts as repo

log = structlog.get_logger(__name__)

#: The worker's PostmortemReview workflow (one per attempt; a retry starts a new run).
REVIEW_WORKFLOW = "PostmortemReview"


def review_workflow_id(attempt_id: str) -> str:
    return f"review-{attempt_id}"


#: For scenarios that don't author a rubric: the parts every postmortem needs.
DEFAULT_RUBRIC = [
    RubricCriterion(
        key="impact",
        max=3,
        description="States who and what was affected, for how long, without overstating it.",
        anchors={"0": "No impact stated.", "3": "Quantified impact, duration and who felt it."},
    ),
    RubricCriterion(
        key="root-cause",
        max=4,
        description="Names the real cause and the mechanism, not just the symptom.",
        anchors={
            "0": "Wrong cause or none.",
            "2": "The right component, but not why it failed.",
            "4": "The cause and the mechanism, matching the facts.",
        },
    ),
    RubricCriterion(
        key="prevention",
        max=3,
        description="Concrete follow-ups that would have caught or prevented it.",
        anchors={"0": "None, or 'be more careful'.", "3": "Specific guards, tests or alerts."},
    ),
]


@dataclass(frozen=True, slots=True)
class View:
    attempt: Attempt
    spec: ScenarioSpec
    scenario: Scenario


async def view(session: AsyncSession, attempt_id: uuid.UUID) -> View | None:
    row = (
        await session.execute(
            select(Attempt, ScenarioVersion.spec, Scenario)
            .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
            .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
            .where(Attempt.id == attempt_id)
        )
    ).one_or_none()
    if row is None:
        return None
    attempt, spec, scenario = row
    return View(attempt, ScenarioSpec.model_validate(spec), scenario)


def root_cause(spec: ScenarioSpec) -> str:
    return spec.ai.root_cause or spec.summary


def rubric(spec: ScenarioSpec) -> list[RubricCriterion]:
    return list(spec.rubric) or DEFAULT_RUBRIC


def personas_in(spec: ScenarioSpec) -> list[str]:
    """Who is in the war room: the scenario's list, else the personas its beats use."""
    if spec.ai.personas:
        return list(spec.ai.personas)
    seen = [b.persona for b in spec.beats if b.persona in teammates.PERSONAS]
    return list(dict.fromkeys(seen)) or list(teammates.PERSONAS)


async def trail(session: AsyncSession, v: View) -> list[coaching.TrailLine]:
    """The player's incident as the replay reads it, redacted, one line per event."""
    rows = (
        await session.execute(
            select(AttemptEvent.id, AttemptEvent.ts, AttemptEvent.type, AttemptEvent.payload)
            .where(AttemptEvent.attempt_id == v.attempt.id, AttemptEvent.type.in_(REPLAY_TYPES))
            .order_by(AttemptEvent.id)
        )
    ).all()
    entries = replay(
        [TrailEvent(ts, type_, payload or {}, id_) for id_, ts, type_, payload in rows],
        v.attempt.active_at,
        v.spec.replay,
    )
    return [
        coaching.TrailLine(e.event_id or 0, e.at_s / 60, redact(e.text)[:300], e.mark)
        for e in entries
    ]


def _speaker(kind: AuthorKind, persona: str | None) -> str:
    if kind is AuthorKind.USER:
        return "You"
    found = teammates.PERSONAS.get(persona or "")
    return found.name if found else (persona or "System").capitalize()


async def conversation(session: AsyncSession, attempt_id: uuid.UUID) -> list[tuple[str, str]]:
    rows = (
        await session.execute(
            select(WarRoomMessage.author_kind, WarRoomMessage.persona_key, WarRoomMessage.body)
            .where(WarRoomMessage.attempt_id == attempt_id)
            .order_by(WarRoomMessage.ts, WarRoomMessage.id)
        )
    ).all()
    return [(_speaker(kind, persona), body) for kind, persona, body in rows]


async def hints_taken(session: AsyncSession, attempt_id: uuid.UUID) -> list[str]:
    rows = await session.scalars(
        select(AttemptEvent.payload)
        .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == "hint")
        .order_by(AttemptEvent.id)
    )
    return [str(p.get("text", "")) for p in rows if isinstance(p, dict)]


async def persona_context(
    session: AsyncSession, v: View, now: datetime | None = None
) -> teammates.Context:
    now = now or datetime.now(UTC)
    a, spec = v.attempt, v.spec
    minutes = int((now - a.active_at).total_seconds() // 60) if a.active_at else 0
    lines = await trail(session, v)
    return teammates.Context(
        title=v.scenario.title,
        story=spec.briefing.story,
        page=f"{spec.page.severity}: {spec.page.title}" if spec.page else "(no page)",
        state=a.state.value,
        minutes=max(0, minutes),
        hints=await hints_taken(session, a.id),
        trail=[line.render() for line in lines],
        conversation=await conversation(session, a.id),
        spoilers=spec.ai.spoilers,
        reveal_at=spec.ai.reveal_at,
        severity=spec.page.severity if spec.page else "SEV3",
        root_cause=root_cause(spec),
        personas=personas_in(spec),
    )


def nudge_direction(spec: ScenarioSpec, taken: int) -> str:
    """The authored hint the nudge leans toward (the next one), never quoted to the player."""
    if spec.hints is None:
        return "Look at what changed and which signal moved first."
    tier = min(3, taken + 1)
    return {1: spec.hints.tier1, 2: spec.hints.tier2, 3: spec.hints.tier3}[tier]


# --------------------------------------------------------------------- after the incident


def _outcome(a: Attempt) -> str:
    score = a.score or {}
    parts = [a.state.value]
    if score.get("mitigation_minutes") is not None:
        parts.append(
            f"mitigated after {score['mitigation_minutes']} min (par {score.get('par_minutes')})"
        )
    parts.append(f"{a.hints_used} hint(s), {score.get('verify_runs', 0)} verify run(s)")
    return ", ".join(parts)


async def _change(session: AsyncSession, attempt_id: uuid.UUID) -> tuple[str, str, bool]:
    """(deployed diff, what the player did to the system, whether anything changed)."""
    diffs = list(
        (
            await session.scalars(
                select(CodeChange.diff)
                .where(CodeChange.attempt_id == attempt_id, CodeChange.deploy_ok.is_(True))
                .order_by(CodeChange.created_at)
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(AttemptEvent.type, AttemptEvent.payload)
            .where(
                AttemptEvent.attempt_id == attempt_id,
                AttemptEvent.type.in_(("action", "deploy", "rollback")),
            )
            .order_by(AttemptEvent.id)
        )
    ).all()
    actions = []
    for type_, p in rows:
        p = p or {}
        if type_ == "action":
            actions.append(f"restarted {p.get('service')}")
        elif type_ == "rollback" and p.get("ok"):
            actions.append(f"rolled {p.get('service')} back to {str(p.get('sha') or '')[:7]}")
        elif type_ == "deploy" and p.get("ok"):
            actions.append(f"deployed {p.get('service')}")
    changed = bool(diffs) or any(t == "rollback" and (p or {}).get("ok") for t, p in rows)
    return "\n".join(diffs), "; ".join(actions) or "(no actions)", changed


async def _probes(session: AsyncSession, attempt_id: uuid.UUID) -> list[str]:
    run = await session.scalar(
        select(VerifyRun)
        .where(VerifyRun.attempt_id == attempt_id)
        .order_by(VerifyRun.created_at.desc())
        .limit(1)
    )
    probes = (run.summary or {}).get("probes", []) if run is not None else []
    return [
        f"{p.get('title', p.get('key'))}: {'pass' if p.get('passed') else 'fail'}" for p in probes
    ]


def _storable(vector: list[float] | None) -> list[float] | None:
    """Only vectors the column holds (a different embedding model would not fit)."""
    return vector if vector is not None and len(vector) == EMBEDDING_DIMENSIONS else None


async def _known(
    session: AsyncSession, llm: Llm, scenario_id: uuid.UUID, meta: CallMeta
) -> tuple[list[Approach], list[cls.Known]]:
    rows = list(
        (
            await session.scalars(
                select(Approach).where(Approach.scenario_id == scenario_id).order_by(Approach.key)
            )
        ).all()
    )
    missing = [a for a in rows if a.embedding is None]
    if missing and llm.enabled("embed"):
        try:
            vectors = await llm.embed(
                [f"{a.name}: {a.idea_md}" for a in missing], CallMeta("embed", meta.user_id)
            )
            for a, vector in zip(missing, vectors, strict=True):
                a.embedding = _storable(vector)
        except AiUnavailable as exc:
            log.info("assist.embed_skipped", reason=exc.reason)
    known = [
        cls.Known(
            a.key,
            a.name,
            a.idea_md,
            a.outcome.value,
            list(a.embedding) if a.embedding is not None else None,
        )
        for a in rows
    ]
    return rows, known


async def review_attempt(
    session_factory: async_sessionmaker[AsyncSession], llm: Llm, attempt_id: uuid.UUID
) -> dict[str, Any] | None:
    """The coach note and, if the rules didn't find it, the approach. Returns what was added."""
    async with session_factory() as session, session.begin():
        v = await view(session, attempt_id)
        if v is None or v.attempt.score is None or v.attempt.user_id is None:
            return None  # not settled yet, or a guest (no AI spend on guests after the fact)
        a = v.attempt
        score = dict(a.score or {})
        added: dict[str, Any] = {}
        user = a.user_id

        if "coach" not in score and llm.enabled("coach"):
            lines = await trail(session, v)
            try:
                meta = CallMeta("coach", user, a.id)
                note = await coaching.coach_note(
                    llm,
                    title=v.scenario.title,
                    root_cause=root_cause(v.spec),
                    outcome=_outcome(a),
                    trail=lines,
                    meta=meta,
                )
                added["coach"] = {
                    "text": note.text,
                    "cites": note.cites,
                    "prompt": prompt("coach").id,
                }
            except AiUnavailable as exc:
                log.info("assist.coach_skipped", attempt_id=str(a.id), reason=exc.reason)

        diff, actions, changed = await _change(session, a.id)
        unrecognised = a.approach_id is None and "approach" not in score
        if unrecognised and changed and llm.enabled("classify"):
            meta = CallMeta("classify", user, a.id)
            try:
                approaches, known = await _known(session, llm, v.scenario.id, meta)
                change = redact(f"{actions}\n{diff}")[:8000]
                vector = None
                if llm.enabled("embed"):
                    vector = (await llm.embed([change], CallMeta("embed", user, a.id)))[0]
                result = await cls.classify(
                    llm,
                    title=v.scenario.title,
                    known=known,
                    diff=diff,
                    actions=actions,
                    probes=await _probes(session, a.id),
                    vector=vector,
                    meta=meta,
                )
                added["approach"] = {
                    "source": "ai",
                    "key": result.key,
                    "confidence": result.confidence,
                    "rationale": result.rationale,
                    "prompt": prompt("classify").id,
                }
                if result.known:
                    a.approach_id = next(x.id for x in approaches if x.key == result.key)
                    a.approach_confidence = result.confidence
                else:
                    session.add(
                        ApproachCandidate(
                            scenario_id=v.scenario.id,
                            attempt_id=a.id,
                            summary=result.rationale[:2000],
                            embedding=_storable(vector),
                        )
                    )
            except AiUnavailable as exc:
                log.info("assist.classify_skipped", attempt_id=str(a.id), reason=exc.reason)

        if added:
            a.score = {**score, **added}
        return added


# ------------------------------------------------------------------------------ grading


async def grade_postmortem(
    session_factory: async_sessionmaker[AsyncSession],
    llm: Llm,
    attempt_id: uuid.UUID,
    *,
    judge_model: str,
) -> grading.Grade | None:
    """Grade a submitted postmortem once (later calls return None). Raises AiUnavailable."""
    async with session_factory() as session:
        v = await view(session, attempt_id)
        doc = await session.scalar(select(Postmortem).where(Postmortem.attempt_id == attempt_id))
        if v is None or doc is None or doc.submitted_at is None:
            return None
        if await session.scalar(
            select(PostmortemGrade.id).where(PostmortemGrade.postmortem_id == doc.id).limit(1)
        ):
            return None
        criteria = rubric(v.spec)
        lines = await trail(session, v)
        _, actions, _ = await _change(session, attempt_id)
        facts = grading.Facts(
            root_cause=root_cause(v.spec),
            timeline=[line.render() for line in lines],
            probes=await _probes(session, attempt_id),
            approach=actions,
        )
        body, user_id = doc.body_md, v.attempt.user_id
    meta = CallMeta("grade", user_id, attempt_id)
    result = await grading.grade(llm, criteria, facts, body, meta)

    async with session_factory() as session, session.begin():
        doc = await session.scalar(
            select(Postmortem).where(Postmortem.attempt_id == attempt_id).with_for_update()
        )
        assert doc is not None
        if await session.scalar(
            select(PostmortemGrade.id).where(PostmortemGrade.postmortem_id == doc.id).limit(1)
        ):
            return None  # a concurrent grader won
        p = prompt("grade")
        session.add(
            PostmortemGrade(
                postmortem_id=doc.id,
                judge_model=judge_model,
                judge_prompt_version=p.id,
                scores=result.as_dict(),
                total=Decimal(str(round(result.fraction, 2))),
                feedback_md=result.feedback,
            )
        )
        attempt = await session.get(Attempt, attempt_id, with_for_update=True)
        if attempt is not None and attempt.score is not None:
            attempt.score = scoring.with_postmortem(attempt.score, result.fraction)
        await repo.add_event(
            session, attempt_id, "review", {"status": "graded", "fraction": result.fraction}
        )
    return result
