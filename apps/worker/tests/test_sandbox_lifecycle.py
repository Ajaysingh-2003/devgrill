"""SandboxLifecycle under Temporal's time-skipping test server, with fake activities.

Proves the lifecycle rules without Docker: TTL expiry, idle timeout (and touch keeping it
alive), abandon, reset, extend limits, verify, faults due after T, a failing provision, and a
worker crash mid-provision. Teardown must run exactly once in every case.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from datetime import datetime, timedelta

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from devgrill.config import Settings
from devgrill.infra.workflows import connect_temporal
from devgrill.sandbox.lifecycle import LaterFault, LifecycleInput, Provisioned
from devgrill_worker.sandbox_activities import ApplyFaultInput, ExtendInput, TeardownInput
from devgrill_worker.sandbox_lifecycle import SandboxLifecycle


class Fakes:
    """Activities with the real names, recording what the workflow asked for."""

    def __init__(
        self,
        *,
        provision_fails: int = 0,
        verify_passes: bool = True,
        later: list[LaterFault] | None = None,
    ) -> None:
        self.calls: Counter[str] = Counter()
        self.teardowns: list[TeardownInput] = []
        self.faults: list[str] = []
        self.extends: list[bool] = []
        self.provision_fails = provision_fails
        self.verify_passes = verify_passes
        self.later = later or []
        self.provisioned_at: datetime | None = None
        self.provisioned = asyncio.Event()
        self.torn_down_at: datetime | None = None

    @property
    def lifetime(self) -> timedelta:
        """Workflow time from the (last) provision to the teardown."""
        assert self.torn_down_at is not None
        assert self.provisioned_at is not None
        return self.torn_down_at - self.provisioned_at

    def activities(self) -> list:
        @activity.defn(name="sandbox.provision")
        async def provision(inp: LifecycleInput) -> Provisioned:
            self.calls["provision"] += 1
            self.provisioned_at = activity.info().scheduled_time
            self.provisioned.set()
            if self.calls["provision"] <= self.provision_fails:
                raise ApplicationError("docker is down")
            return Provisioned("dg-test", list(self.later))

        @activity.defn(name="sandbox.reset")
        async def reset(inp: LifecycleInput) -> Provisioned:
            self.calls["reset"] += 1
            return Provisioned("dg-test", list(self.later))

        @activity.defn(name="sandbox.apply_fault")
        async def apply_fault(inp: ApplyFaultInput) -> None:
            self.faults.append(inp.use)

        @activity.defn(name="sandbox.extended")
        async def extended(inp: ExtendInput) -> None:
            self.extends.append(inp.granted)

        @activity.defn(name="sandbox.verify")
        async def verify(inp: LifecycleInput) -> bool:
            self.calls["verify"] += 1
            return self.verify_passes

        @activity.defn(name="sandbox.teardown")
        async def teardown(inp: TeardownInput) -> None:
            self.teardowns.append(inp)
            self.torn_down_at = activity.info().scheduled_time

        return [provision, reset, apply_fault, extended, verify, teardown]


def lifecycle_input(**kw: object) -> LifecycleInput:
    base = {
        "attempt_id": str(uuid.uuid4()),
        "scenario_slug": "ttl-zero",
        "tier": "free",
        "ttl_minutes": 30,
        "idle_minutes": 8,
    }
    return LifecycleInput(**{**base, **kw})  # type: ignore[arg-type]


@pytest.fixture
async def env():
    try:
        environment = await WorkflowEnvironment.start_time_skipping()
    except Exception as exc:
        pytest.skip(f"time-skipping test server unavailable: {exc}")
    async with environment:
        yield environment


async def run(env: WorkflowEnvironment, fakes: Fakes, inp: LifecycleInput, script=None) -> str:
    queue = f"q-{uuid.uuid4().hex[:8]}"
    async with Worker(
        env.client, task_queue=queue, workflows=[SandboxLifecycle], activities=fakes.activities()
    ):
        handle = await env.client.start_workflow(
            SandboxLifecycle.run, inp, id=f"wf-{uuid.uuid4().hex[:8]}", task_queue=queue
        )
        if script is not None:
            await script(handle)
        return await handle.result()


async def test_ttl_expiry_tears_down(env):
    fakes = Fakes()
    # idle longer than the TTL so the TTL is what ends it
    assert await run(env, fakes, lifecycle_input(ttl_minutes=30, idle_minutes=60)) == "expired"
    assert [t.outcome for t in fakes.teardowns] == ["expired"]
    assert fakes.teardowns[0].reason == "time limit reached"
    assert timedelta(minutes=29) <= fakes.lifetime <= timedelta(minutes=31)


async def test_idle_timeout_and_touch(env):
    fakes = Fakes()

    async def keep_touching(handle):
        for _ in range(3):
            await env.sleep(timedelta(minutes=5))
            await handle.signal("touch")

    # touched every 5 minutes for 15 minutes, then idle for 8 -> ends at ~23 min, not at 8
    assert await run(env, fakes, lifecycle_input(idle_minutes=8), keep_touching) == "expired"
    assert timedelta(minutes=22) <= fakes.lifetime <= timedelta(minutes=24)
    assert fakes.teardowns[0].reason == "idle timeout"


async def test_abandon(env):
    fakes = Fakes()

    async def abandon(handle):
        await env.sleep(timedelta(minutes=1))
        await handle.signal("abandon")

    assert await run(env, fakes, lifecycle_input(), abandon) == "abandoned"
    assert [t.outcome for t in fakes.teardowns] == ["abandoned"]


async def test_reset_is_limited_and_keeps_the_deadline(env):
    fakes = Fakes()

    async def reset_a_lot(handle):
        for _ in range(5):
            await env.sleep(timedelta(minutes=1))
            await handle.signal("reset")
            await handle.signal("touch")

    assert (
        await run(env, fakes, lifecycle_input(ttl_minutes=20, idle_minutes=60), reset_a_lot)
        == "expired"
    )
    assert fakes.calls["reset"] == 3
    assert len(fakes.teardowns) == 1


async def test_extend_is_granted_up_to_the_plan(env):
    fakes = Fakes()

    async def extend_thrice(handle):
        for _ in range(3):
            await handle.signal("extend")
        await env.sleep(timedelta(seconds=1))
        status = await handle.query(SandboxLifecycle.status)
        assert status.extends_used == 2

    inp = lifecycle_input(ttl_minutes=30, idle_minutes=120, extend_minutes=15, max_extends=2)
    assert await run(env, fakes, inp, extend_thrice) == "expired"
    assert fakes.extends == [True, True, False]
    assert timedelta(minutes=59) <= fakes.lifetime <= timedelta(minutes=61)


async def test_verify_pass_resolves(env):
    fakes = Fakes(verify_passes=True)

    async def verify(handle):
        await env.sleep(timedelta(minutes=2))
        await handle.signal("verify")

    assert await run(env, fakes, lifecycle_input(), verify) == "resolved"
    assert [t.outcome for t in fakes.teardowns] == ["resolved"]


async def test_verify_fail_returns_to_the_incident(env):
    fakes = Fakes(verify_passes=False)

    async def verify(handle):
        await env.sleep(timedelta(minutes=2))
        await handle.signal("verify")

    assert await run(env, fakes, lifecycle_input(idle_minutes=60), verify) == "expired"
    assert fakes.calls["verify"] == 1


async def test_faults_due_after_t_fire_on_time(env):
    fakes = Fakes(later=[LaterFault(90, "db/lock-migration"), LaterFault(30, "cache/ttl-zero")])
    assert await run(env, fakes, lifecycle_input(ttl_minutes=10, idle_minutes=60)) == "expired"
    assert fakes.faults == ["cache/ttl-zero", "db/lock-migration"]


async def test_provision_that_keeps_failing_still_tears_down(env):
    fakes = Fakes(provision_fails=99)
    assert await run(env, fakes, lifecycle_input()) == "failed"
    assert fakes.calls["provision"] == 3  # the retry policy, then give up
    assert [t.outcome for t in fakes.teardowns] == ["failed"]


async def test_provision_retry_recovers(env):
    fakes = Fakes(provision_fails=1)

    async def abandon(handle):
        await env.sleep(timedelta(minutes=1))
        await handle.signal("abandon")

    assert await run(env, fakes, lifecycle_input(), abandon) == "abandoned"
    assert fakes.calls["provision"] == 2


async def test_cancellation_tears_down(env):
    fakes = Fakes()

    async def cancel(handle):
        await env.sleep(timedelta(minutes=1))
        await handle.cancel()

    with pytest.raises(WorkflowFailureError):
        await run(env, fakes, lifecycle_input(), cancel)
    assert [t.outcome for t in fakes.teardowns] == ["abandoned"]


@pytest.mark.integration
async def test_worker_crash_mid_provision() -> None:
    """The first worker dies while provisioning; another worker picks the attempt up.

    Real Temporal dev server (`just deps-up`): the time-skipping server won't fast-forward
    while it holds an orphaned activity. Costs one real heartbeat timeout (30 s).
    """
    client = await connect_temporal(Settings(_env_file=None))  # type: ignore[call-arg]
    queue = f"q-{uuid.uuid4().hex[:8]}"
    started = asyncio.Event()

    @activity.defn(name="sandbox.provision")
    async def hanging_provision(inp: LifecycleInput) -> Provisioned:
        started.set()
        await asyncio.sleep(3600)  # never heartbeats
        raise AssertionError("unreachable")

    crashed = Fakes()
    others = [a for a in crashed.activities() if a.__name__ != "provision"]
    inp = lifecycle_input(idle_minutes=60, ttl_minutes=30)
    async with Worker(
        client,
        task_queue=queue,
        workflows=[SandboxLifecycle],
        activities=[hanging_provision, *others],
    ):
        handle = await client.start_workflow(
            SandboxLifecycle.run, inp, id=f"wf-{uuid.uuid4().hex[:8]}", task_queue=queue
        )
        await started.wait()
    # The first worker is gone mid-provision. A fresh one takes over once the heartbeat
    # timeout fires and the retry policy schedules provision again.
    second = Fakes()
    async with Worker(
        client, task_queue=queue, workflows=[SandboxLifecycle], activities=second.activities()
    ):
        await asyncio.wait_for(second.provisioned.wait(), 90)
        await handle.signal("abandon")
        assert await handle.result() == "abandoned"
    assert second.calls["provision"] == 1
    assert [t.outcome for t in second.teardowns] == ["abandoned"]
