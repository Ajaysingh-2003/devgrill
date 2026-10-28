"""The verify activities against real Postgres (fake sandbox driver): what a run stores.

The workflow tests use fake activities; this runs the real ones in Temporal's activity
environment, so the rows, events and state moves of a verify run are checked end to end.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from temporalio.testing import ActivityEnvironment

from devgrill.config import Settings
from devgrill.domain.enums import AttemptMode, AttemptState, VerifyStatus
from devgrill.infra import db
from devgrill.infra.models import Attempt, AttemptEvent, ProbeResult, Scenario, VerifyRun
from devgrill.sandbox.content import load_bundle
from devgrill.sandbox.driver import ExecResult, MetricSnapshot, ResourceUsage
from devgrill_content.seed import seed
from devgrill_worker.sandbox_activities import (
    ProbeGroupInput,
    SandboxActivities,
    VerifyFinishInput,
    VerifyInput,
)

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"


class FakeDriver:
    """k6 and Postgres answer as for a fixed system; the app's metrics aren't scraped."""

    def __init__(self) -> None:
        self.scans = 100.0
        self.load: list[str] = []

    async def stop_load(self, handle: Any) -> None:
        self.load.append("stop")

    async def start_load(self, handle: Any, bundle: Any) -> None:
        self.load.append("start")

    async def usage(self, handle: Any, service: str | None = None) -> ResourceUsage:
        return ResourceUsage(cpu_seconds=0.0, memory_bytes=200 * 1_048_576)  # steady memory

    async def metrics(self, handle: Any, bundle: Any) -> MetricSnapshot:
        return MetricSnapshot(datetime.now(UTC), {})

    async def probe(self, handle: Any, argv: list[str], *, timeout_s: int = 60) -> ExecResult:
        if argv[0] == "dg-sql":
            self.scans += 300
            row = json.dumps({"scans": self.scans, "reset": "t0"})
            return ExecResult(0, json.dumps({"columns": ["x"], "rows": [[row]]}), "")
        if argv[0] == "redis-cli":
            return ExecResult(0, "maxmemory\n268435456\n", "")
        if argv[0] == "sh" and argv[2].startswith("cat "):
            return ExecResult(
                0, json.dumps({"p99_ms": 90.0, "error_rate": 0.0, "requests": 1800}), ""
            )
        if argv[0] == "sh" and "python3" in argv[2]:
            return ExecResult(0, json.dumps({"checks": 15, "checks_failed": 0, "failures": []}), "")
        return ExecResult(0, "", "")


@pytest.fixture
async def setup(db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from devgrill.sandbox import verifier

    monkeypatch.setattr(verifier, "STATS_SETTLE_S", 0)
    await seed(db_session, CONTENT)
    scenario = await db_session.scalar(select(Scenario).where(Scenario.slug == "ttl-zero"))
    assert scenario is not None and scenario.current_version_id is not None
    attempt = Attempt(
        guest_token_hash=uuid.uuid4().hex,
        scenario_version_id=scenario.current_version_id,
        mode=AttemptMode.ONCALL,
        state=AttemptState.MITIGATED,
    )
    db_session.add(attempt)
    await db_session.commit()
    driver = FakeDriver()
    bundle = load_bundle(CONTENT, "ttl-zero")
    acts = SandboxActivities(
        settings=Settings(_env_file=None),  # type: ignore[call-arg]
        driver=driver,  # type: ignore[arg-type]
        session_factory=db.create_session_factory(db_engine),
        valkey=None,
        bundle_loader=lambda slug: bundle,
    )
    return acts, driver, attempt.id, db_session


async def test_a_run_stores_its_results_and_goes_back_when_it_fails(setup) -> None:  # type: ignore[no-untyped-def]
    acts, driver, attempt_id, session = setup
    env = ActivityEnvironment()
    begun = await env.run(acts.verify_begin, VerifyInput(str(attempt_id), "ttl-zero", 1))
    assert begun.previous_state == "mitigated"
    assert begun.groups[0] == ["sale-replay", "db-offload", "honest-metrics"]
    again = await env.run(acts.verify_begin, VerifyInput(str(attempt_id), "ttl-zero", 1))
    assert again.run_id == begun.run_id and again.previous_state == "mitigated"  # retried: same run

    for keys in begun.groups:
        await env.run(
            acts.verify_probes, ProbeGroupInput(str(attempt_id), "ttl-zero", begun.run_id, keys)
        )
    passed = await env.run(
        acts.verify_finish,
        VerifyFinishInput(str(attempt_id), "ttl-zero", begun.run_id, begun.previous_state),
    )
    # The app's metrics aren't scraped here, so honest-metrics can't be measured: it fails.
    assert passed is False

    session.expire_all()
    run = await session.get(VerifyRun, uuid.UUID(begun.run_id))
    assert run is not None and run.status is VerifyStatus.PARTIAL
    by_key = {p["key"]: p for p in run.summary["probes"]}  # type: ignore[index]
    assert by_key["db-offload"]["passed"] is True
    assert by_key["db-offload"]["measured"] == {
        "db_scans_per_request": pytest.approx(0.1667, abs=1e-3)
    }
    assert by_key["honest-metrics"]["passed"] is False
    results = (
        await session.scalars(select(ProbeResult).where(ProbeResult.verify_run_id == run.id))
    ).all()
    assert len(results) == 5
    attempt = await session.get(Attempt, attempt_id)
    assert attempt is not None and attempt.state is AttemptState.MITIGATED  # back where it was
    assert driver.load == ["stop", "stop", "start"]
    types = (
        await session.scalars(
            select(AttemptEvent.type)
            .where(AttemptEvent.attempt_id == attempt_id)
            .order_by(AttemptEvent.id)
        )
    ).all()
    # "started" from each begin (the retry re-announces it), then running and done per probe.
    assert types.count("verify_progress") == 2 + 2 * 5
    verdict = types.index("verify")
    assert types[verdict + 1] == "state"  # the verdict, then the move back


async def test_a_run_that_breaks_on_our_side_is_an_error(setup) -> None:  # type: ignore[no-untyped-def]
    acts, _, attempt_id, session = setup
    env = ActivityEnvironment()
    begun = await env.run(acts.verify_begin, VerifyInput(str(attempt_id), "ttl-zero", 1))
    passed = await env.run(
        acts.verify_finish,
        VerifyFinishInput(
            str(attempt_id), "ttl-zero", begun.run_id, begun.previous_state, "docker is down"
        ),
    )
    assert passed is False
    session.expire_all()
    run = await session.get(VerifyRun, uuid.UUID(begun.run_id))
    assert run is not None and run.status is VerifyStatus.ERROR
    event = await session.scalar(
        select(AttemptEvent.payload)
        .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.type == "verify")
        .limit(1)
    )
    assert event is not None and "doesn't count" in event["error"]
    assert all(p["passed"] is None for p in event["probes"])  # not run, not failed
