"""AI in the workspace and the debrief (ADR 016), against real Postgres and Valkey. The model
is a FakeLlm: these test what the platform does with answers, refusals and outages."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devgrill.ai import teammates
from devgrill.ai.classify import ClassifyOutput
from devgrill.ai.coaching import CoachOutput, NudgeOutput
from devgrill.ai.grading import GradeOutput
from devgrill.ai.port import AiUnavailable, FakeLlm
from devgrill.domain.enums import AttemptMode, AuthorKind
from devgrill.domain.streaks import DEFAULT_TIMEZONE, activity_day
from devgrill.infra import assist
from devgrill.infra.models import (
    ApproachCandidate,
    Attempt,
    AttemptEvent,
    CodeChange,
    LlmCall,
    WarRoomMessage,
)
from devgrill.infra.settle import settle
from devgrill_api.assist import drain
from devgrill_api.routers.attempts import _assist
from devgrill_api.testing import finish, rules, started

pytestmark = pytest.mark.integration


def use(api, llm: FakeLlm) -> FakeLlm:  # type: ignore[no-untyped-def]
    api.app.state.llm = llm
    return llm


def settle_tasks(api) -> None:  # type: ignore[no-untyped-def]
    api.portal.call(drain, api.app.state)


async def events(session: AsyncSession, attempt_id: uuid.UUID, type_: str) -> list[dict]:
    rows = await session.scalars(
        select(AttemptEvent.payload)
        .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == type_)
        .order_by(AttemptEvent.id)
    )
    return list(rows)


# ---------------------------------------------------------------------------- teammates


async def test_a_teammate_answers_in_the_war_room(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    llm = use(api, FakeLlm({"persona": ["Which signal moved first: latency or errors?"]}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    res = api.post(
        f"/v1/attempts/{attempt_id}/messages",
        json={"text": "@Priya what's the impact?"},
        headers=headers,
    )
    assert res.status_code == 204
    settle_tasks(api)
    [reply] = await events(seeded, attempt_id, "reply")
    assert reply["persona"] == "priya"
    assert reply["text"] == "Which signal moved first: latency or errors?"
    message = await seeded.scalar(
        select(WarRoomMessage).where(
            WarRoomMessage.attempt_id == attempt_id,
            WarRoomMessage.author_kind == AuthorKind.PERSONA,
        )
    )
    assert message is not None and message.persona_key == "priya"
    # The player's message reached the model fenced, as data.
    _, meta, _, user = llm.calls[0]
    assert meta.attempt_id == attempt_id and meta.feature == "persona"
    assert '<data source="war-room">' in user and "what's the impact?" in user


async def test_a_reply_that_gives_the_cause_away_is_replaced(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    use(api, FakeLlm({"persona": ["It's DATABASE_URL, someone pointed it at postgres-dr."]}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    api.post(f"/v1/attempts/{attempt_id}/messages", json={"text": "any idea?"}, headers=headers)
    settle_tasks(api)
    [reply] = await events(seeded, attempt_id, "reply")
    assert reply["text"] == teammates.PERSONAS["arjun"].safe_line
    assert "postgres-dr" not in str(await events(seeded, attempt_id, "reply"))


async def test_teammates_stay_quiet_without_ai_or_a_war_room(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    use(api, FakeLlm({"persona": ["hello"]}, disabled={"persona"}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    api.post(f"/v1/attempts/{attempt_id}/messages", json={"text": "hi"}, headers=headers)
    llm = use(api, FakeLlm({"persona": ["hello"]}))
    ttl_zero, ttl_headers = await started(api, seeded, auth)  # no war_room tool
    api.post(f"/v1/attempts/{ttl_zero}/messages", json={"text": "hi"}, headers=ttl_headers)
    settle_tasks(api)
    assert await events(seeded, attempt_id, "reply") == []
    assert await events(seeded, ttl_zero, "reply") == []
    assert llm.calls == []


async def test_a_model_outage_records_no_reply(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    use(api, FakeLlm({"persona": [AiUnavailable("budget", "spent")]}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    api.post(f"/v1/attempts/{attempt_id}/messages", json={"text": "hi"}, headers=headers)
    settle_tasks(api)
    assert await events(seeded, attempt_id, "reply") == []


async def test_the_daily_allowance_caps_replies(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    llm = use(api, FakeLlm({"persona": ["ok"]}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    attempt = await seeded.get(Attempt, attempt_id)
    assert attempt is not None
    day = activity_day(datetime.now(UTC), DEFAULT_TIMEZONE).isoformat()
    # The free plan's 20 a day, already used.
    api.portal.call(api.app.state.valkey.set, f"ai:messages:user:{attempt.user_id}:{day}", 20)
    api.post(f"/v1/attempts/{attempt_id}/messages", json={"text": "hi"}, headers=headers)
    settle_tasks(api)
    assert llm.calls == []
    assert await events(seeded, attempt_id, "reply") == []
    nudge = api.post(f"/v1/attempts/{attempt_id}/nudge", headers=headers)
    assert (nudge.status_code, nudge.json()["code"]) == (429, "ai_allowance")


def test_assist_announcements_are_forwarded_and_row_announcements_are_not() -> None:
    assert _assist({"data": '{"assist": {"id": "1", "kind": "delta", "text": "hi"}}'}) == (
        '{"id": "1", "kind": "delta", "text": "hi"}'
    )
    assert _assist({"data": b'{"assist": {"id": "1", "kind": "busy"}}'}) is not None
    assert _assist({"data": "1"}) is None
    assert _assist(None) is None
    assert _assist({"data": "{not json"}) is None


# -------------------------------------------------------------------------------- nudges


async def test_guided_mode_gets_a_nudge(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    llm = use(
        api,
        FakeLlm(
            {"nudge": [NudgeOutput(nudge="Compare where requests wait with how busy Postgres is.")]}
        ),
    )
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    res = api.post(f"/v1/attempts/{attempt_id}/nudge", headers=headers)
    assert res.status_code == 201, res.text
    assert res.json()["text"].startswith("Compare where requests wait")
    assert [e["text"] for e in await events(seeded, attempt_id, "nudge")] == [res.json()["text"]]
    # It leans on the next authored hint, given to the model only.
    assert "hint" not in res.json()["text"].lower()
    assert llm.calls[0][1].feature == "nudge"


async def test_a_nudge_that_leaks_is_refused(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    use(api, FakeLlm({"nudge": [NudgeOutput(nudge="Check DATABASE_URL.")]}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    res = api.post(f"/v1/attempts/{attempt_id}/nudge", headers=headers)
    assert (res.status_code, res.json()["code"]) == (503, "ai_unavailable")
    assert await events(seeded, attempt_id, "nudge") == []


async def test_no_nudges_on_call(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    use(api, FakeLlm({"nudge": [NudgeOutput(nudge="x")]}))
    attempt_id, headers = await started(api, seeded, auth, slug="pool-party")
    await seeded.execute(
        update(Attempt).where(Attempt.id == attempt_id).values(mode=AttemptMode.ONCALL)
    )
    await seeded.commit()
    res = api.post(f"/v1/attempts/{attempt_id}/nudge", headers=headers)
    assert (res.status_code, res.json()["code"]) == (409, "no_nudges")


# ----------------------------------------------------------------------- after the incident

POSTMORTEM = {
    "summary": "Product reads hit Postgres directly after the ops deploy.",
    "impact": "Postgres load tripled for 10 minutes; no errors reached customers.",
    "cause": "The ops deploy set CACHE_TTL_SECONDS=0, so nothing was cached.",
    "actions": "Validate cache config in CI; alert when the hit rate drops.",
}


def grade_reply() -> GradeOutput:
    return GradeOutput.model_validate(
        {
            "criteria": [
                {
                    "key": "impact",
                    "score": 3,
                    "evidence": ["Postgres load tripled for 10 minutes"],
                    "reason": "Quantified.",
                },
                {
                    "key": "root-cause",
                    "score": 4,
                    "evidence": ["set CACHE_TTL_SECONDS=0, so nothing was cached"],
                    "reason": "Cause and mechanism.",
                },
                {
                    "key": "prevention",
                    "score": 3,
                    "evidence": ["alert when the hit rate drops"],
                    "reason": "Concrete guards.",
                },
            ],
            "blameless": True,
            "blame": [],
            "feedback": "Clear and blameless. Add who owns each action.",
        }
    )


async def test_a_submitted_postmortem_is_reviewed(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    orchestrator, _ = fakes
    use(api, FakeLlm({"grade": [grade_reply()]}))
    attempt_id, headers = await started(api, seeded, auth)
    await finish(seeded, attempt_id)
    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()

    res = api.post(
        f"/v1/attempts/{attempt_id}/postmortem/submit",
        json={"sections": POSTMORTEM},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["review"] == {**res.json()["review"], "status": "pending"}
    assert orchestrator.reviews == [str(attempt_id)]

    # The worker's activity, on the test's loop.
    factory = async_sessionmaker(seeded.bind, expire_on_commit=False)
    grade = await assist.grade_postmortem(
        factory, FakeLlm({"grade": [grade_reply()]}), attempt_id, judge_model="gpt-6.1-sol"
    )
    assert grade is not None and grade.total == 10
    again = await assist.grade_postmortem(
        factory, FakeLlm({"grade": [grade_reply()]}), attempt_id, judge_model="gpt-6.1-sol"
    )
    assert again is None  # graded once

    review = api.get(f"/v1/attempts/{attempt_id}/postmortem", headers=headers).json()["review"]
    assert review["status"] == "graded"
    assert [c["key"] for c in review["criteria"]] == ["impact", "root-cause", "prevention"]
    assert review["fraction"] == 1.0 and review["blameless"] is True
    debrief = api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers).json()
    assert debrief["review"]["status"] == "graded"
    assert debrief["score"]["postmortem"] == 1.0 and debrief["score"]["total"] is not None
    # Ratings never move with the postmortem.
    attempt = await seeded.get(Attempt, attempt_id)
    assert attempt is not None
    await seeded.refresh(attempt)
    assert attempt.score is not None and attempt.score["incident"] == 1.0
    again = api.post(f"/v1/attempts/{attempt_id}/postmortem/review", headers=headers)
    assert (again.status_code, again.json()["code"]) == (409, "already_reviewed")


async def test_reviews_are_unavailable_without_ai_and_can_be_asked_again(
    api, seeded, auth, fakes
) -> None:  # type: ignore[no-untyped-def]
    orchestrator, _ = fakes
    use(api, FakeLlm(disabled={"grade"}))
    attempt_id, headers = await started(api, seeded, auth)
    await finish(seeded, attempt_id)
    submitted = api.post(
        f"/v1/attempts/{attempt_id}/postmortem/submit",
        json={"sections": POSTMORTEM},
        headers=headers,
    ).json()
    assert submitted["review"]["status"] == "unavailable"
    assert "off" in submitted["review"]["detail"]
    assert orchestrator.reviews == []

    use(api, FakeLlm({"grade": [grade_reply()]}))
    orchestrator.fail_reviews = True
    res = api.post(f"/v1/attempts/{attempt_id}/postmortem/review", headers=headers)
    assert (res.status_code, res.json()["status"]) == (202, "failed")
    orchestrator.fail_reviews = False
    res = api.post(f"/v1/attempts/{attempt_id}/postmortem/review", headers=headers)
    assert (res.status_code, res.json()["status"]) == (202, "pending")
    assert orchestrator.reviews == [str(attempt_id)]


async def test_the_coach_and_the_classifier_read_a_finished_attempt(
    api, seeded, auth, fakes
) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    await finish(seeded, attempt_id, rolled_back=False)
    seeded.add(
        CodeChange(
            attempt_id=attempt_id,
            diff="--- a/app/cache.py\n+++ b/app/cache.py\n-    if ttl == 0:\n+    if ttl < 0:\n",
            files=["app/cache.py"],
            deploy_ok=True,
        )
    )
    await seeded.commit()
    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    attempt = await seeded.get(Attempt, attempt_id)
    assert attempt is not None and attempt.approach_id is None  # the rules don't know it

    trail_ids = list(
        (
            await seeded.scalars(
                select(AttemptEvent.id).where(
                    AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == "trail"
                )
            )
        ).all()
    )
    llm = FakeLlm(
        {
            "coach": [
                CoachOutput(
                    note=f"The query stats were the clue [e{trail_ids[0]}]; [e999999] is invented.",
                    cites=[trail_ids[0], 999999],
                )
            ],
            "classify": [
                ClassifyOutput(
                    key="unknown",
                    confidence=0.7,
                    rationale="Changed the app to treat a TTL of 0 as a real TTL.",
                )
            ],
        },
        vector=lambda text: [1.0] + [0.0] * 1535,
    )
    factory = async_sessionmaker(seeded.bind, expire_on_commit=False)
    added = await assist.review_attempt(factory, llm, attempt_id)
    assert added is not None and set(added) == {"coach", "approach"}
    assert await assist.review_attempt(factory, llm, attempt_id) == {}  # idempotent

    debrief = api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers).json()
    assert debrief["coach"]["cites"] == [trail_ids[0]]
    assert "[e999999]" not in debrief["coach"]["text"]
    assert debrief["approach_note"]["source"] == "ai"
    assert debrief["approach_note"]["rationale"].startswith("Changed the app")  # resolved
    assert trail_ids[0] in [e["event_id"] for e in debrief["replay"]]
    candidate = await seeded.scalar(
        select(ApproachCandidate).where(ApproachCandidate.attempt_id == attempt_id)
    )
    assert candidate is not None and candidate.status == "open"

    admin = auth(uuid.uuid4(), login="root-admin")
    groups = api.get("/v1/admin/approach-candidates", headers=admin).json()
    assert any(c["attempt_id"] == str(attempt_id) for g in groups for c in g["candidates"])
    res = api.post(
        f"/v1/admin/approach-candidates/{candidate.id}", json={"status": "dismissed"}, headers=admin
    )
    assert res.status_code == 204


async def test_guests_get_no_review_after_the_fact(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, _ = await started(api, seeded, auth)
    await seeded.execute(
        update(Attempt).where(Attempt.id == attempt_id).values(user_id=None, guest_token_hash="g")
    )
    await finish(seeded, attempt_id)
    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    factory = async_sessionmaker(seeded.bind, expire_on_commit=False)
    assert await assist.review_attempt(factory, FakeLlm(), attempt_id) is None


async def test_admin_sees_ai_spend(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, _ = await started(api, seeded, auth)
    for feature, cost, status in (
        ("persona", "0.0004", "ok"),
        ("grade", "0.0200", "ok"),
        ("grade", "0", "error"),
    ):
        seeded.add(
            LlmCall(
                feature=feature,
                model="gpt-6-luna",
                prompt_version=f"{feature}@1",
                input_tokens=100,
                output_tokens=50,
                cost_usd=Decimal(cost),
                latency_ms=900,
                attempt_id=attempt_id,
                status=status,
            )
        )
    await seeded.commit()
    body = api.get("/v1/admin/ai/costs", headers=auth(uuid.uuid4(), login="root-admin")).json()
    assert body["spent_today_usd"] >= 0.0204
    grade = next(f for f in body["features"] if f["feature"] == "grade")
    assert (grade["calls"], grade["errors"]) >= (2, 1)
    assert body["per_attempt_usd"] is not None and body["days"]
