"""Wave 7E: the content console's roles (authors can't publish, reviewers can't edit content),
the scenario lifecycle, the audit log, analytics, and user lookup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain import admin as policy
from devgrill.domain.enums import AttemptMode, AttemptState, Role, ScenarioStatus
from devgrill.infra.models import Attempt, AuditLog, Scenario
from devgrill_content.seed import seed

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"


def _with_roles(api: TestClient, auth, login: str, roles: list[str]) -> dict[str, str]:  # type: ignore[no-untyped-def]
    """Headers for a new user holding `roles` (granted by the configured admin)."""
    user = uuid.uuid4()
    headers = auth(user, login=login)
    api.get("/v1/me", headers=headers)
    root = auth(uuid.uuid4(), login="root-admin")
    granted = api.put(f"/v1/admin/users/{user}/roles", json={"roles": roles}, headers=root)
    assert granted.status_code == 200, granted.text
    return headers


# ------------------------------------------------------------------------------ the policy


def test_the_gate_rules_hold_in_the_policy() -> None:
    author, reviewer = [Role.AUTHOR.value], [Role.REVIEWER.value]
    # Authors can't publish (or retire, or send back); they submit drafts.
    assert policy.actions_for(author, ScenarioStatus.REVIEW) == []
    assert policy.actions_for(author, ScenarioStatus.DRAFT) == [policy.Action.SUBMIT]
    # Reviewers can't edit content: they decide, never submit.
    assert policy.actions_for(reviewer, ScenarioStatus.DRAFT) == []
    assert set(policy.actions_for(reviewer, ScenarioStatus.REVIEW)) == {
        policy.Action.SEND_BACK,
        policy.Action.PUBLISH,
    }
    # Only admins manage users or read the audit log.
    for role in (Role.USER, Role.AUTHOR, Role.REVIEWER):
        assert not policy.allowed([role.value], policy.Permission.MANAGE_USERS)
        assert not policy.allowed([role.value], policy.Permission.VIEW_AUDIT)
    assert all(policy.allowed([Role.ADMIN.value], p) for p in policy.Permission)


def test_flags_need_enough_attempts() -> None:
    quiet = {
        "solve_rate": 0.0,
        "abandon_rate": 1.0,
        "median_minutes": 99.0,
        "hints_per_attempt": 3.0,
    }
    assert policy.flags(attempts=9, est_minutes=10, **quiet) == []
    assert len(policy.flags(attempts=10, est_minutes=10, **quiet)) == 4


# ------------------------------------------------------------------------------ the API


async def test_authors_submit_reviewers_decide_and_every_step_is_audited(
    api: TestClient, seeded: AsyncSession, auth
) -> None:  # type: ignore[no-untyped-def]
    author = _with_roles(api, auth, "ana-author", ["author"])
    reviewer = _with_roles(api, auth, "rey-reviewer", ["reviewer"])

    # Retire a published scenario as the reviewer, then restore it.
    retire = "/v1/admin/scenarios/ttl-zero/actions/retire"
    assert api.post(retire, json={}, headers=author).status_code == 403
    assert api.post(retire, json={}, headers=reviewer).json()["status"] == "retired"
    restore = api.post("/v1/admin/scenarios/ttl-zero/actions/restore", json={}, headers=reviewer)
    assert restore.json()["status"] == "published"

    # A draft (a new scenario arriving from content): the author submits it, the author can't
    # publish it, the reviewer can't submit it.
    draft = "ghost-reads"
    scenario = (await seeded.execute(select(Scenario).where(Scenario.slug == draft))).scalar_one()
    scenario.status = ScenarioStatus.DRAFT
    await seeded.commit()
    listing = {s["slug"]: s for s in api.get("/v1/admin/scenarios", headers=author).json()["items"]}
    assert listing[draft]["actions"] == ["submit"]
    assert (
        api.post(
            f"/v1/admin/scenarios/{draft}/actions/submit", json={}, headers=reviewer
        ).status_code
        == 403
    )
    assert (
        api.post(f"/v1/admin/scenarios/{draft}/actions/submit", json={}, headers=author).json()[
            "status"
        ]
        == "review"
    )
    assert (
        api.post(
            f"/v1/admin/scenarios/{draft}/actions/publish", json={}, headers=author
        ).status_code
        == 403
    )
    # Sending back needs a reason.
    assert (
        api.post(
            f"/v1/admin/scenarios/{draft}/actions/send_back", json={}, headers=reviewer
        ).json()["code"]
        == "note_required"
    )
    back = api.post(
        f"/v1/admin/scenarios/{draft}/actions/send_back",
        json={"note": "The clue is too faint"},
        headers=reviewer,
    )
    assert back.json()["status"] == "draft"
    # Wrong state: 409, and nothing changes.
    assert (
        api.post(f"/v1/admin/scenarios/{draft}/actions/retire", json={}, headers=reviewer).json()[
            "code"
        ]
        == "invalid_transition"
    )

    root = auth(uuid.uuid4(), login="root-admin")
    log = api.get("/v1/admin/audit", headers=root).json()
    actions = [(e["action"], e["actor"], e["target"]) for e in reversed(log)]
    assert ("scenario.retire", "rey-reviewer", "scenario:ttl-zero") in actions
    assert ("scenario.submit", "ana-author", f"scenario:{draft}") in actions
    sent_back = next(e for e in log if e["action"] == "scenario.send_back")
    assert sent_back["data"] == {"from": "review", "to": "draft", "note": "The clue is too faint"}
    assert sum(a == "user.roles" for a, _, _ in actions) == 2
    # Authors and reviewers can't read the audit log or manage users.
    assert api.get("/v1/admin/audit", headers=reviewer).status_code == 403
    assert api.get("/v1/admin/users", params={"q": "an"}, headers=author).status_code == 403


def test_console_permissions_and_reports(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    author = _with_roles(api, auth, "aki-author", ["author"])
    me = api.get("/v1/admin/me", headers=author).json()
    assert me == {"roles": ["author", "user"], "permissions": ["submit", "view_console"]}
    assert api.get("/v1/admin/me", headers=auth(uuid.uuid4(), login="plain")).status_code == 403
    report = api.get("/v1/admin/scenarios/ttl-zero/report", headers=author).json()
    assert report["slug"] == "ttl-zero" and report["version"] == 1
    assert api.get("/v1/admin/scenarios/nope/report", headers=author).status_code == 404


async def test_analytics_and_flags(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    reviewer = _with_roles(api, auth, "rio-reviewer", ["reviewer"])
    owner = uuid.uuid4()
    api.get("/v1/me", headers=auth(owner, login="player-one"))
    version = await seeded.scalar(
        select(Scenario.current_version_id).where(Scenario.slug == "pool-party")
    )
    start = datetime(2026, 10, 1, tzinfo=UTC)
    # 12 finished runs: 1 solved in 40 minutes (est 15), 8 abandoned, 3 failed, 3 hints each.
    states = [AttemptState.RESOLVED] + [AttemptState.ABANDONED] * 8 + [AttemptState.FAILED] * 3
    for i, state in enumerate(states):
        seeded.add(
            Attempt(
                user_id=owner,
                scenario_version_id=version,
                mode=AttemptMode.GUIDED,
                state=state,
                active_at=start + timedelta(hours=i),
                resolved_at=start + timedelta(hours=i, minutes=40)
                if state is AttemptState.RESOLVED
                else None,
                ended_at=start + timedelta(hours=i, minutes=41),
                hints_used=3,
            )
        )
    await seeded.commit()
    rows = {r["slug"]: r for r in api.get("/v1/admin/analytics/scenarios", headers=reviewer).json()}
    pool = rows["pool-party"]
    assert pool["attempts"] == 12
    assert pool["solve_rate"] == round(1 / 12, 3)
    assert pool["abandon_rate"] == round(8 / 12, 3)
    assert pool["median_minutes"] == 40.0
    assert set(pool["flags"]) == {
        "Solve rate under 10%",
        "Median time over twice the estimate",
        "Over half of players leave",
        "Most players need two or more hints",
    }
    assert rows["ttl-zero"]["attempts"] == 0 and rows["ttl-zero"]["flags"] == []


def test_user_lookup_and_roles(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    root_id = uuid.uuid4()
    root = auth(root_id, login="root-admin")
    target = uuid.uuid4()
    api.get("/v1/me", headers=auth(target, login="support-me"))
    found = api.get("/v1/admin/users", params={"q": "suppo"}, headers=root).json()
    assert [u["handle"] for u in found] == ["support-me"]
    assert found[0]["roles"] == ["user"] and found[0]["plan"] == "free"
    # "user" is always kept; admins can't drop their own admin role.
    set_roles = api.put(
        f"/v1/admin/users/{target}/roles", json={"roles": ["reviewer"]}, headers=root
    )
    assert set_roles.json()["roles"] == ["reviewer", "user"]
    api.get("/v1/me", headers=root)
    own = api.put(f"/v1/admin/users/{root_id}/roles", json={"roles": []}, headers=root)
    assert own.json()["code"] == "own_admin"
    # Wildcards are literal.
    assert api.get("/v1/admin/users", params={"q": "%%"}, headers=root).json() == []


async def test_reseeding_keeps_the_console_status(
    api: TestClient, seeded: AsyncSession, auth
) -> None:  # type: ignore[no-untyped-def]
    reviewer = _with_roles(api, auth, "ray-reviewer", ["reviewer"])
    api.post("/v1/admin/scenarios/pool-party/actions/retire", json={}, headers=reviewer)
    await seed(seeded, CONTENT)
    await seeded.commit()
    status = await seeded.scalar(select(Scenario.status).where(Scenario.slug == "pool-party"))
    assert status is ScenarioStatus.RETIRED
    assert (await seeded.scalar(select(func.count()).select_from(AuditLog)) or 0) >= 2
