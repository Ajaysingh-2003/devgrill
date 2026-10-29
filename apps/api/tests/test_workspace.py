"""Workspace endpoints against real Postgres and Valkey (fake gateway, fake Temporal)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select, update

from devgrill.domain.enums import AttemptState
from devgrill.infra.models import Attempt, AttemptEvent, WarRoomMessage
from devgrill.infra.signing import redeem_ticket
from devgrill_api.errors import AppError
from devgrill_api.testing import started

pytestmark = pytest.mark.integration


async def test_workspace_describes_the_incident(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    body = api.get(f"/v1/attempts/{attempt_id}/workspace", headers=headers).json()
    assert body["scenario_title"] == "TTL zero"
    assert body["page"] == {
        "severity": "SEV4",
        "title": "postgres: product reads 3x normal (capacity alert)",
    }
    assert body["slo"]["db_qps_product"] == {"lt": 75.0, "gt": None}
    assert "cache_hit_rate" in body["metrics"]
    assert body["deployable"] == ["api", "worker"]
    assert (body["hints_total"], body["hints"]) == (3, [])
    assert body["unlocked_tools"] == ["overview", "logs", "terminal", "cache", "code", "deploys"]
    _, stranger = await started(api, seeded, auth)
    assert api.get(f"/v1/attempts/{attempt_id}/workspace", headers=stranger).status_code == 404


async def test_ws_tickets_are_bound_to_the_attempt(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    res = api.post(
        f"/v1/attempts/{attempt_id}/ws-ticket", json={"kind": "terminal"}, headers=headers
    )
    assert res.status_code == 201
    body = res.json()
    assert body["url"].endswith(f"/gw/v1/attempts/{attempt_id}/terminal?ticket={body['ticket']}")
    assert api.portal is not None
    ticket = api.portal.call(redeem_ticket, api.app.state.valkey, body["ticket"])  # type: ignore[attr-defined]
    assert (ticket.attempt_id, ticket.kind) == (str(attempt_id), "terminal")
    assert ticket.owner.startswith("user:")
    bad = api.post(f"/v1/attempts/{attempt_id}/ws-ticket", json={"kind": "root"}, headers=headers)
    assert bad.status_code == 422
    # Someone else's attempt: no ticket, and no hint that it exists.
    _, stranger = await started(api, seeded, auth)
    res = api.post(
        f"/v1/attempts/{attempt_id}/ws-ticket", json={"kind": "terminal"}, headers=stranger
    )
    assert res.status_code == 404


async def test_hints_reveal_in_order_and_are_counted(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    tiers = [
        api.post(f"/v1/attempts/{attempt_id}/hints", headers=headers).json()["tier"]
        for _ in range(3)
    ]
    assert tiers == [1, 2, 3]
    done = api.post(f"/v1/attempts/{attempt_id}/hints", headers=headers)
    assert (done.status_code, done.json()["code"]) == (409, "no_more_hints")
    assert [
        h["tier"] for h in api.get(f"/v1/attempts/{attempt_id}/hints", headers=headers).json()
    ] == [1, 2, 3]
    hints_used = await seeded.scalar(select(Attempt.hints_used).where(Attempt.id == attempt_id))
    assert hints_used == 3


async def test_status_updates_go_to_the_war_room(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    res = api.post(
        f"/v1/attempts/{attempt_id}/messages",
        json={"text": "Rolling back a91f3c2"},
        headers=headers,
    )
    assert res.status_code == 204
    message = await seeded.scalar(
        select(WarRoomMessage).where(WarRoomMessage.attempt_id == attempt_id)
    )
    assert message is not None and message.body == "Rolling back a91f3c2"
    assert (
        api.post(
            f"/v1/attempts/{attempt_id}/messages", json={"text": ""}, headers=headers
        ).status_code
        == 422
    )


async def test_declared_mitigation_is_checked_against_reality(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    attempt_id, headers = await started(api, seeded, auth)
    early = api.post(f"/v1/attempts/{attempt_id}/mitigation", headers=headers).json()
    assert early == {"declared": True, "real_state": "active", "correct": False}
    await seeded.execute(
        update(Attempt).where(Attempt.id == attempt_id).values(state=AttemptState.MITIGATED)
    )
    await seeded.commit()
    right = api.post(f"/v1/attempts/{attempt_id}/mitigation", headers=headers).json()
    assert right["correct"] is True
    claims = (
        await seeded.scalars(
            select(AttemptEvent.payload).where(
                AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == "mitigation"
            )
        )
    ).all()
    assert [c["correct"] for c in claims] == [False, True]


async def test_sandbox_operations_go_through_the_gateway(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    orchestrator, gateway = fakes
    attempt_id, headers = await started(api, seeded, auth)
    base = f"/v1/attempts/{attempt_id}"
    assert api.get(f"{base}/status", headers=headers).json()["services"][0]["name"] == "api"
    assert api.get(f"{base}/files", headers=headers).json()["files"] == ["app/main.py"]
    assert (
        api.get(f"{base}/file", params={"path": "app/main.py"}, headers=headers).json()["content"]
        == "x = 1\n"
    )
    assert api.put(
        f"{base}/file", params={"path": "app/main.py"}, json={"content": "x = 2\n"}, headers=headers
    ).json()["saved"]
    assert api.post(f"{base}/deploys", json={}, headers=headers).json()["ok"] is True
    assert (
        api.post(f"{base}/rollbacks", json={"ref": "1234abc"}, headers=headers).json()["sha"]
        == "1234abc"
    )
    assert api.post(f"{base}/rollbacks", json={"ref": "HEAD~1"}, headers=headers).status_code == 422
    assert api.post(f"{base}/restarts", json={"service": "api"}, headers=headers).json() == {
        "message": "api restarted"
    }
    assert api.get(f"{base}/db", headers=headers).json()["top"][0]["calls"] == 5
    assert api.post(f"{base}/db/query", json={"sql": "SELECT 1"}, headers=headers).json()[
        "rows"
    ] == [[1]]
    assert api.get(f"{base}/cache", headers=headers).json()["asked"][0]["exists"] is False
    assert api.get(f"{base}/deploys", headers=headers).json()["live"] == "abc"
    changes = api.get(f"{base}/deploys/abc1234", headers=headers).json()
    assert (changes["files"], changes["message"]) == (
        ["config/app.env"],
        "config: use the new HA database endpoint",
    )
    assert api.get(f"{base}/deploys/HEAD~1", headers=headers).status_code in (404, 422)
    assert ("PUT", "file", {"path": "app/main.py"}, {"content": "x = 2\n"}) in gateway.calls
    assert (str(attempt_id), "touch") in orchestrator.signals  # player activity resets idle


async def test_gateway_refusals_become_problems(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    _, gateway = fakes
    attempt_id, headers = await started(api, seeded, auth)
    gateway.fail = AppError(400, "bad_path", "'../x' is not a file in this repo")
    res = api.get(f"/v1/attempts/{attempt_id}/file", params={"path": "../x"}, headers=headers)
    assert (res.status_code, res.json()["code"]) == (400, "bad_path")


async def test_ended_attempts_refuse_operations(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    _, gateway = fakes
    attempt_id, headers = await started(api, seeded, auth, state=AttemptState.EXPIRED)
    res = api.get(f"/v1/attempts/{attempt_id}/status", headers=headers)
    assert (res.status_code, res.json()["code"]) == (409, "attempt_ended")
    assert gateway.calls == []
    # The workspace itself still renders (the "incident ended" screen).
    assert api.get(f"/v1/attempts/{attempt_id}/workspace", headers=headers).status_code == 200


async def test_hidden_events_never_reach_the_player(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    from devgrill.infra.repositories import attempts as repo

    attempt_id, headers = await started(api, seeded, auth)
    await repo.add_event(seeded, attempt_id, "fault", {"use": "cache/ttl-zero"})
    await repo.add_event(seeded, attempt_id, "trail", {"verb": "sql"})
    await repo.add_event(seeded, attempt_id, "sandbox", {"action": "destroyed"})
    await seeded.commit()
    with api.stream("GET", f"/v1/attempts/{attempt_id}/events", headers=headers) as res:
        types = [
            json.loads(line[5:])["type"] for line in res.iter_lines() if line.startswith("data:")
        ]
    assert "fault" not in types and "trail" not in types
    assert types[-1] == "sandbox"


async def test_touch_resets_idle_and_workspace_reports_idle(api, seeded, auth, fakes) -> None:  # type: ignore[no-untyped-def]
    orchestrator, _ = fakes
    attempt_id, headers = await started(api, seeded, auth)
    assert api.post(f"/v1/attempts/{attempt_id}/touch", headers=headers).status_code == 204
    assert orchestrator.signals[-1] == (str(attempt_id), "touch")
    assert (
        api.get(f"/v1/attempts/{attempt_id}/workspace", headers=headers).json()["idle_minutes"] == 8
    )
