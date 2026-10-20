"""Attempt endpoints and the ADR 013 limits, against real Postgres and Valkey (fake Temporal)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import AttemptMode, AttemptState, Plan
from devgrill.infra.models import Attempt, Entitlement, Scenario
from devgrill.infra.repositories import attempts as repo
from devgrill.sandbox.lifecycle import LifecycleInput
from devgrill_api.orchestrator import OrchestratorError
from devgrill_content.seed import seed

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"


class FakeOrchestrator:
    def __init__(self) -> None:
        self.started: list[LifecycleInput] = []
        self.signals: list[tuple[str, str]] = []
        self.fail = False

    async def start(self, inp: LifecycleInput) -> None:
        if self.fail:
            raise OrchestratorError("temporal is down")
        self.started.append(inp)

    async def signal(self, attempt_id: str, name: str) -> None:
        self.signals.append((attempt_id, name))


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed(db_session, CONTENT)
    await db_session.commit()
    return db_session


@pytest.fixture
def fake(api: TestClient) -> FakeOrchestrator:
    orchestrator = FakeOrchestrator()
    api.app.state.orchestrator = orchestrator  # type: ignore[attr-defined]
    return orchestrator


def settings(api: TestClient):
    return api.app.state.settings  # type: ignore[attr-defined]


def user_headers(auth, login: str = "player") -> tuple[uuid.UUID, dict[str, str]]:  # type: ignore[no-untyped-def]
    user = uuid.uuid4()
    return user, auth(user, login=f"{login}-{user.hex[:6]}")


async def make_pro(session: AsyncSession, user: uuid.UUID) -> None:
    await session.execute(
        update(Entitlement).where(Entitlement.user_id == user).values(plan=Plan.PRO)
    )
    await session.commit()


async def past_attempts(
    session: AsyncSession, user: uuid.UUID, count: int, *, minutes_each: float = 5
) -> None:
    """Ended attempts this week, each with a sandbox session of `minutes_each`."""
    version = await session.scalar(
        text("SELECT current_version_id FROM app.scenarios WHERE slug = 'ttl-zero'")
    )
    now = datetime.now(UTC)
    for _ in range(count):
        attempt = Attempt(
            user_id=user,
            scenario_version_id=version,
            mode=AttemptMode.GUIDED,
            state=AttemptState.EXPIRED,
            started_at=now - timedelta(minutes=minutes_each + 1),
            ended_at=now,
        )
        session.add(attempt)
        await session.flush()
        await session.execute(
            text(
                "INSERT INTO app.sandbox_sessions"
                " (attempt_id, driver, state, resources, created_at, ready_at, destroyed_at)"
                " VALUES (:a, 'compose', 'destroyed', '{\"tier\": \"free\"}', :c, :r, :d)"
            ),
            {
                "a": attempt.id,
                "c": now - timedelta(minutes=minutes_each + 1),
                "r": now - timedelta(minutes=minutes_each),
                "d": now,
            },
        )
    await session.commit()


def start(api: TestClient, headers: dict[str, str], slug: str = "ttl-zero"):
    return api.post("/v1/attempts", json={"scenario_slug": slug}, headers=headers)


# --------------------------------------------------------------------------------- start


async def test_free_user_starts_a_free_incident(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    _, headers = user_headers(auth)
    res = start(api, headers)
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["state"] == "provisioning" and body["scenario_slug"] == "ttl-zero"
    assert res.headers["location"] == f"/v1/attempts/{body['id']}"
    [inp] = fake.started
    assert (inp.attempt_id, inp.tier, inp.ttl_minutes, inp.idle_minutes) == (
        body["id"],
        "free",
        30,
        8,
    )
    assert api.get(f"/v1/attempts/{body['id']}", headers=headers).json()["state"] == "provisioning"


async def test_pro_incident_needs_pro(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    user, headers = user_headers(auth)
    denied = start(api, headers, "big-sale-meltdown")
    assert (denied.status_code, denied.json()["code"]) == (403, "upgrade_required")
    assert denied.headers["content-type"].startswith("application/problem+json")
    assert fake.started == []
    await make_pro(seeded, user)
    granted = start(api, headers, "big-sale-meltdown")
    assert granted.status_code == 202
    assert fake.started[0].ttl_minutes == 45  # the scenario's own TTL, under Pro's 60


async def test_one_live_attempt(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    _, headers = user_headers(auth)
    assert start(api, headers).status_code == 202
    again = start(api, headers, "pool-party")
    assert (again.status_code, again.json()["code"]) == (409, "active_attempt_exists")


async def test_weekly_starts_quota(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    user, headers = user_headers(auth)
    api.get("/v1/me", headers=headers)  # creates the profile and its entitlements row
    await past_attempts(seeded, user, 3)
    res = start(api, headers)
    assert (res.status_code, res.json()["code"]) == (429, "quota_exceeded")
    assert 0 < int(res.headers["retry-after"]) <= 7 * 24 * 3600
    assert fake.started == []


async def test_minutes_quota_caps_the_session(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    user, headers = user_headers(auth)
    api.get("/v1/me", headers=headers)
    await past_attempts(seeded, user, 2, minutes_each=50)  # 100 of 120 minutes used
    assert start(api, headers).status_code == 202
    assert 19 <= fake.started[0].ttl_minutes <= 20


async def test_fleet_capacity(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    settings(api).sandbox_max_live = 1
    _, first = user_headers(auth, "first")
    _, second = user_headers(auth, "second")
    assert start(api, first).status_code == 202
    full = start(api, second)
    assert (full.status_code, full.json()["code"], full.headers["retry-after"]) == (
        503,
        "capacity",
        "60",
    )


async def test_budget_kill_switch_spares_pro(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    settings(api).sandbox_free_starts = False
    _, free_headers = user_headers(auth, "free")
    paused = start(api, free_headers)
    assert (paused.status_code, paused.json()["code"]) == (503, "budget_paused")
    assert api.get("/v1/me/usage", headers=free_headers).json()["free_paused"] is True
    pro, pro_headers = user_headers(auth, "pro")
    api.get("/v1/me", headers=pro_headers)
    await make_pro(seeded, pro)
    assert start(api, pro_headers).status_code == 202


async def test_guests_play_the_tutorial_only(api, seeded, fake) -> None:  # type: ignore[no-untyped-def]
    token = api.post("/v1/guest-tokens").json()["token"]
    headers = {"X-Guest-Token": token}
    other = start(api, headers, "pool-party")
    assert (other.status_code, other.json()["code"]) == (403, "sign_up_required")
    tutorial = start(api, headers)
    assert tutorial.status_code == 202
    assert (fake.started[0].tier, fake.started[0].ttl_minutes) == ("guest", 20)
    assert api.get("/v1/me/usage", headers=headers).json()["live_starts"] == {
        "used": 1,
        "limit": 1,
        "period": "ever",
        "resets_at": None,
    }


def test_anonymous_callers_are_turned_away(api, seeded, fake) -> None:  # type: ignore[no-untyped-def]
    res = start(api, {})
    assert (res.status_code, res.json()["code"]) == (401, "unauthenticated")


async def test_unplayable_and_unknown_scenarios(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    _, headers = user_headers(auth)
    assert start(api, headers, "no-such-incident").status_code == 404
    placeholder = start(api, headers, "ghost-reads")
    assert (placeholder.status_code, placeholder.json()["code"]) == (409, "not_playable")


async def test_orchestrator_failure_fails_the_attempt(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    fake.fail = True
    user, headers = user_headers(auth)
    res = start(api, headers)
    assert (res.status_code, res.json()["code"]) == (503, "capacity")
    state = await seeded.scalar(
        text("SELECT state::text FROM app.attempts WHERE user_id = :u"), {"u": user}
    )
    assert state == "failed"
    fake.fail = False
    assert start(api, headers).status_code == 202  # the failed one doesn't block a retry


# ---------------------------------------------------------------------------- steering


async def test_steering_signals_and_ownership(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    _, headers = user_headers(auth)
    attempt_id = start(api, headers).json()["id"]
    for path, signal in (("extend", "extend"), ("reset", "reset"), ("verify", "verify")):
        assert api.post(f"/v1/attempts/{attempt_id}/{path}", headers=headers).status_code == 202
        assert (attempt_id, signal) in fake.signals
    assert api.delete(f"/v1/attempts/{attempt_id}", headers=headers).status_code == 202
    assert fake.signals[-1] == (attempt_id, "abandon")

    _, stranger = user_headers(auth, "stranger")
    assert api.get(f"/v1/attempts/{attempt_id}", headers=stranger).status_code == 404
    assert api.delete(f"/v1/attempts/{attempt_id}", headers=stranger).status_code == 404


async def test_ended_attempts_cannot_be_steered(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    _, headers = user_headers(auth)
    attempt_id = uuid.UUID(start(api, headers).json()["id"])
    await repo.move(seeded, attempt_id, AttemptState.ABANDONED)
    await seeded.commit()
    res = api.post(f"/v1/attempts/{attempt_id}/extend", headers=headers)
    assert (res.status_code, res.json()["code"]) == (409, "attempt_ended")


async def test_events_stream_until_teardown(api, seeded, auth, fake) -> None:  # type: ignore[no-untyped-def]
    _, headers = user_headers(auth)
    attempt_id = uuid.UUID(start(api, headers).json()["id"])
    await repo.move(seeded, attempt_id, AttemptState.ACTIVE)
    await repo.move(seeded, attempt_id, AttemptState.EXPIRED, reason="time limit reached")
    await repo.add_event(seeded, attempt_id, "sandbox", {"action": "destroyed"})
    await seeded.commit()

    with api.stream("GET", f"/v1/attempts/{attempt_id}/events", headers=headers) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        data = [json.loads(line[5:]) for line in res.iter_lines() if line.startswith("data:")]
    states = [d["payload"]["to"] for d in data if d["type"] == "state"]
    assert states == ["provisioning", "active", "expired"]
    assert data[-1]["payload"] == {"action": "destroyed"}

    # Resumable: after the second event only the rest arrives.
    with api.stream(
        "GET", f"/v1/attempts/{attempt_id}/events", headers={**headers, "Last-Event-ID": "0"}
    ) as res:
        ids = [line[3:].strip() for line in res.iter_lines() if line.startswith("id:")]
    with api.stream(
        "GET", f"/v1/attempts/{attempt_id}/events", headers={**headers, "Last-Event-ID": ids[1]}
    ) as res:
        rest = [line[3:].strip() for line in res.iter_lines() if line.startswith("id:")]
    assert rest == ids[2:]


async def test_scenario_access_is_stored(seeded) -> None:  # type: ignore[no-untyped-def]
    rows = dict((await seeded.execute(text("SELECT slug, access::text FROM app.scenarios"))).all())
    assert rows["ttl-zero"] == "free" and rows["pool-party"] == "free"
    assert rows["big-sale-meltdown"] == "pro" and rows["ghost-reads"] == "pro"
    assert Scenario.access is not None
