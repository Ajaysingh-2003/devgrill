"""Settling, the debrief and the postmortem, against real Postgres (ADR 015)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import AttemptState
from devgrill.infra.models import (
    ActivityDay,
    Approach,
    Attempt,
    Probe,
    RatingHistory,
    Scenario,
    SkillRating,
)
from devgrill.infra.settle import settle
from devgrill_api.testing import PROBES, finish, rules, started

pytestmark = pytest.mark.integration

# --------------------------------------------------------------------------------- seed


async def test_seed_stores_probes_and_known_approaches(seeded: AsyncSession) -> None:
    scenario = await seeded.scalar(select(Scenario).where(Scenario.slug == "ttl-zero"))
    assert scenario is not None
    keys = set(
        (
            await seeded.scalars(
                select(Probe.key).where(Probe.scenario_version_id == scenario.current_version_id)
            )
        ).all()
    )
    assert keys == set(PROBES)
    approaches = set(
        (
            await seeded.scalars(select(Approach.key).where(Approach.scenario_id == scenario.id))
        ).all()
    )
    assert approaches == {"restore-ttl", "rollback"}  # cheats never reach the database


# ------------------------------------------------------------------------------- settle


async def test_settle_scores_rates_and_recognises_the_approach(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, _ = await started(api, seeded, auth)
    await finish(seeded, attempt_id)
    scenario_before = await seeded.scalar(
        select(Scenario.rating).where(Scenario.slug == "ttl-zero")
    )

    score = await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    assert score is not None
    assert score["resolution"] == 1.0
    assert score["mitigation_time"] == 1.0  # 4 minutes, par 5, and verify held the SLO
    assert score["communication"] == 1.0  # two status updates
    assert score["incident"] == 1.0 and score["total"] is None  # postmortem pending

    attempt = await seeded.get(Attempt, attempt_id)
    assert attempt is not None
    await seeded.refresh(attempt)
    assert attempt.rating_delta is not None and attempt.rating_delta["delta"] > 0
    approach = await seeded.get(Approach, attempt.approach_id)
    assert approach is not None and approach.key == "rollback"
    rating = await seeded.scalar(select(SkillRating).where(SkillRating.user_id == attempt.user_id))
    assert rating is not None and rating.games == 1
    assert (await seeded.scalar(select(Scenario.rating).where(Scenario.slug == "ttl-zero"))) < (
        scenario_before or 0
    )
    day = await seeded.scalar(select(ActivityDay).where(ActivityDay.user_id == attempt.user_id))
    assert day is not None and day.kinds == ["incident"]

    # Settling again changes nothing (worker retries).
    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    history = await seeded.scalar(
        select(func.count())
        .select_from(RatingHistory)
        .where(RatingHistory.attempt_id == attempt_id)
    )
    assert history == 1


async def test_attempt_history_shows_the_settled_result(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    before = api.get("/v1/me/attempts", headers=headers).json()["items"][0]
    assert (before["score"], before["rating_delta"]) == (None, None)
    await finish(seeded, attempt_id)
    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    item = api.get("/v1/me/attempts", headers=headers).json()["items"][0]
    assert item["score"] == 1.0 and item["rating_delta"] > 0
    assert item["mitigation_minutes"] == 4.0


async def test_an_expired_attempt_scores_its_partial_fix(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, _ = await started(api, seeded, auth)
    await finish(
        seeded, attempt_id, state=AttemptState.EXPIRED, failing=("db-offload",), rolled_back=False
    )
    score = await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    assert score is not None
    assert score["resolution"] == pytest.approx(3.5 / 4.5, abs=1e-3)
    # Mitigation was detected, but verify didn't hold the SLO (db-offload failed): no credit.
    assert score["mitigation_time"] == 0.0
    attempt = await seeded.get(Attempt, attempt_id)
    assert attempt is not None
    await seeded.refresh(attempt)
    assert attempt.approach_id is None
    assert attempt.rating_delta is not None  # running out of time is a rated result


async def test_still_live_attempts_are_not_settled(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, _ = await started(api, seeded, auth)
    assert await settle(seeded, attempt_id) is None


# ------------------------------------------------------------------------------ debrief


async def test_debrief_after_the_incident(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    res = api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers)
    assert (res.status_code, res.json()["code"]) == (409, "still_live")

    await finish(seeded, attempt_id)
    pending = api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers).json()
    assert pending["settled"] is False and pending["score"] is None

    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    body = api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers).json()
    assert body["settled"] is True
    assert body["score"]["incident"] == 1.0
    assert body["rating"]["delta"] > 0 and body["rating"]["track_slug"] == "caching"
    assert [p["key"] for p in body["verify"]["probes"]] == PROBES
    sale = next(p for p in body["verify"]["probes"] if p["key"] == "sale-replay")
    assert sale["target"]["p99_ms"] == {"lt": 500.0, "gt": None}
    assert body["approach_key"] == "rollback"
    assert {a["key"]: a["yours"] for a in body["approaches"]} == {
        "restore-ttl": False,
        "rollback": True,
    }
    assert {a["key"]: a["share"] for a in body["approaches"]} == {"restore-ttl": 0, "rollback": 100}
    assert body["mastery"]["after"] > body["mastery"]["before"]  # a first resolution
    texts = [(e["text"], e["mark"]) for e in body["replay"]]
    assert ("Queried the database: select * from pg_stat_statements", "clue") in texts
    assert any(t.startswith("Rolled api back") for t, _ in texts)
    assert "big-sale-meltdown" in [n["slug"] for n in body["next"]]
    assert body["postmortem"] == "none"

    _, stranger = await started(api, seeded, auth)
    assert api.get(f"/v1/attempts/{attempt_id}/debrief", headers=stranger).status_code == 404


async def test_approaches_stay_hidden_until_resolved(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    await finish(seeded, attempt_id, state=AttemptState.EXPIRED, failing=("db-offload",))
    await settle(seeded, attempt_id, approach_rules=rules())
    await seeded.commit()
    body = api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers).json()
    assert body["approaches"] is None
    assert body["verify"]["status"] == "failed"


async def test_verify_is_idempotent_while_running(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    orchestrator, _ = fakes
    attempt_id, headers = await started(api, seeded, auth, state=AttemptState.VERIFYING)
    res = api.post(f"/v1/attempts/{attempt_id}/verify", headers=headers)
    assert res.status_code == 202 and res.json()["state"] == "verifying"
    assert orchestrator.signals == []  # the run in progress answers it
    provisioning, headers2 = await started(api, seeded, auth, state=AttemptState.PROVISIONING)
    res = api.post(f"/v1/attempts/{provisioning}/verify", headers=headers2)
    assert (res.status_code, res.json()["code"]) == (409, "not_ready")


# ---------------------------------------------------------------------------- postmortem


async def test_postmortem_draft_then_submit(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    url = f"/v1/attempts/{attempt_id}/postmortem"
    assert api.get(url, headers=headers).status_code == 409  # still live
    await finish(seeded, attempt_id)

    empty = api.get(url, headers=headers).json()
    assert empty["sections"] == {"summary": "", "impact": "", "cause": "", "actions": ""}
    assert any("Paged" in line for line in empty["timeline"])

    draft = {"sections": {"summary": "Product reads hit Postgres.", "cause": "TTL set to 0."}}
    saved = api.put(url, json=draft, headers=headers).json()
    assert saved["sections"]["summary"] == "Product reads hit Postgres."
    assert saved["submitted_at"] is None
    assert api.get(url, headers=headers).json()["sections"]["cause"] == "TTL set to 0."

    blank = api.post(f"{url}/submit", json={"sections": {"summary": "  "}}, headers=headers)
    assert (blank.status_code, blank.json()["code"]) == (422, "empty_postmortem")
    done = api.post(f"{url}/submit", json=draft, headers=headers)
    assert done.status_code == 200 and done.json()["submitted_at"] is not None
    again = api.put(url, json=draft, headers=headers)
    assert (again.status_code, again.json()["code"]) == (409, "already_submitted")

    from devgrill.infra.models import Postmortem

    doc = await seeded.scalar(select(Postmortem).where(Postmortem.attempt_id == attempt_id))
    assert doc is not None
    await seeded.refresh(doc)
    assert "## Root cause\n\nTTL set to 0." in doc.body_md
    assert "## Timeline" in doc.body_md
    assert (
        api.get(f"/v1/attempts/{attempt_id}/debrief", headers=headers).json()["postmortem"]
        == "submitted"
    )
