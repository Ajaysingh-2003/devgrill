"""SandboxLifecycle: one workflow per attempt, from provisioning to guaranteed teardown.

  provision (boot, faults due before T, load)  ->  active
  active: timers for faults due after T, the TTL and the idle timeout;
          signals: abandon, reset, extend, verify, touch (player activity)
  finally: teardown (measure, destroy, close the session, settle the attempt's state)

Deterministic: no I/O, clocks or randomness here; activities do all of it. The teardown runs
in `finally`, so expiry, abandonment, failures, cancellation and worker crashes all end in it.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from devgrill.sandbox.lifecycle import (
        MAX_RESETS,
        QUERY_STATUS,
        SIGNAL_ABANDON,
        SIGNAL_EXTEND,
        SIGNAL_RESET,
        SIGNAL_TOUCH,
        SIGNAL_VERIFY,
        WORKFLOW_NAME,
        LaterFault,
        LifecycleInput,
        LifecycleStatus,
        Provisioned,
    )
    from devgrill_worker.sandbox_activities import (
        ApplyFaultInput,
        ExtendInput,
        SandboxActivities,
        TeardownInput,
    )

PROVISION_TIMEOUT = timedelta(minutes=5)
PROVISION_HEARTBEAT = timedelta(seconds=30)
PROVISION_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=3)
STEP_TIMEOUT = timedelta(minutes=3)
STEP_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3)
VERIFY_TIMEOUT = timedelta(minutes=10)
# Teardown retries until Docker answers again (bounded by its schedule-to-close).
TEARDOWN_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2), maximum_interval=timedelta(minutes=1)
)
TEARDOWN_DEADLINE = timedelta(hours=2)


@workflow.defn(name=WORKFLOW_NAME)
class SandboxLifecycle:
    def __init__(self) -> None:
        self._state = "provisioning"
        self._abandon = False
        self._reset = False
        self._verify = False
        self._extend_requests = 0
        self._touched = False
        self._expires_at: datetime | None = None
        self._extends_used = 0
        self._resets_used = 0
        self._reason = ""

    # ----------------------------------------------------------------- signals, query

    @workflow.signal(name=SIGNAL_ABANDON)
    def abandon(self) -> None:
        self._abandon = True

    @workflow.signal(name=SIGNAL_RESET)
    def reset(self) -> None:
        self._reset = True

    @workflow.signal(name=SIGNAL_EXTEND)
    def extend(self) -> None:
        self._extend_requests += 1

    @workflow.signal(name=SIGNAL_VERIFY)
    def verify(self) -> None:
        self._verify = True

    @workflow.signal(name=SIGNAL_TOUCH)
    def touch(self) -> None:
        self._touched = True

    @workflow.query(name=QUERY_STATUS)
    def status(self) -> LifecycleStatus:
        return LifecycleStatus(
            state=self._state,
            expires_at=self._expires_at.isoformat() if self._expires_at else None,
            extends_used=self._extends_used,
            resets_used=self._resets_used,
        )

    # ---------------------------------------------------------------------------- run

    @workflow.run
    async def run(self, inp: LifecycleInput) -> str:
        outcome = "failed"
        try:
            provisioned: Provisioned = await workflow.execute_activity_method(
                SandboxActivities.provision,
                inp,
                start_to_close_timeout=PROVISION_TIMEOUT,
                heartbeat_timeout=PROVISION_HEARTBEAT,
                retry_policy=PROVISION_RETRY,
            )
            outcome = "abandoned" if self._abandon else await self._play(inp, provisioned)
        except ActivityError as exc:
            workflow.logger.warning("sandbox step failed", extra={"attempt_id": inp.attempt_id})
            outcome = "failed"
            self._reason = str(exc.cause or exc)[:500]
        except asyncio.CancelledError:
            outcome = "abandoned"
            raise
        finally:
            self._state = "tearing_down"
            await workflow.execute_activity_method(
                SandboxActivities.teardown,
                TeardownInput(inp.attempt_id, outcome, self._reason),
                start_to_close_timeout=STEP_TIMEOUT,
                schedule_to_close_timeout=TEARDOWN_DEADLINE,
                retry_policy=TEARDOWN_RETRY,
            )
            self._state = outcome
        return outcome

    async def _play(self, inp: LifecycleInput, provisioned: Provisioned) -> str:
        self._state = "active"
        start = workflow.now()
        deadline = start + timedelta(minutes=inp.ttl_minutes)
        idle = timedelta(minutes=inp.idle_minutes)
        idle_deadline = start + idle
        self._expires_at = deadline
        pending: list[LaterFault] = sorted(provisioned.later_faults, key=lambda f: f.at_seconds)

        while True:
            now = workflow.now()
            wake = min(
                [
                    deadline,
                    idle_deadline,
                    *(start + timedelta(seconds=f.at_seconds) for f in pending[:1]),
                ]
            )
            with contextlib.suppress(TimeoutError):
                await workflow.wait_condition(
                    lambda: (
                        self._abandon
                        or self._reset
                        or self._verify
                        or self._touched
                        or self._extend_requests > 0
                    ),
                    timeout=max(wake - now, timedelta(0)),
                )
            now = workflow.now()

            if self._abandon:
                self._reason = "abandoned by the player"
                return "abandoned"
            if self._touched:
                self._touched = False
                idle_deadline = now + idle
            while self._extend_requests > 0:
                self._extend_requests -= 1
                granted = self._extends_used < inp.max_extends and inp.extend_minutes > 0
                if granted:
                    self._extends_used += 1
                    deadline += timedelta(minutes=inp.extend_minutes)
                    self._expires_at = deadline
                await workflow.execute_activity_method(
                    SandboxActivities.extended,
                    ExtendInput(inp.attempt_id, granted, deadline.isoformat()),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )
                idle_deadline = now + idle
            if self._reset:
                self._reset = False
                if self._resets_used < MAX_RESETS:
                    self._resets_used += 1
                    self._state = "resetting"
                    provisioned = await workflow.execute_activity_method(
                        SandboxActivities.reset,
                        inp,
                        start_to_close_timeout=PROVISION_TIMEOUT,
                        heartbeat_timeout=PROVISION_HEARTBEAT,
                        retry_policy=PROVISION_RETRY,
                    )
                    self._state = "active"
                    # The incident restarts; the session's deadline does not.
                    start = workflow.now()
                    pending = sorted(provisioned.later_faults, key=lambda f: f.at_seconds)
                    idle_deadline = start + idle
            if self._verify:
                self._verify = False
                self._state = "verifying"
                passed: bool = await workflow.execute_activity_method(
                    SandboxActivities.verify,
                    inp,
                    start_to_close_timeout=VERIFY_TIMEOUT,
                    heartbeat_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                if passed:
                    return "resolved"
                self._state = "active"
                idle_deadline = workflow.now() + idle
            now = workflow.now()
            while pending and start + timedelta(seconds=pending[0].at_seconds) <= now:
                fault = pending.pop(0)
                await workflow.execute_activity_method(
                    SandboxActivities.apply_fault,
                    ApplyFaultInput(inp.attempt_id, inp.scenario_slug, fault.use, fault.params),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )
            if now >= deadline:
                self._reason = "time limit reached"
                return "expired"
            if now >= idle_deadline:
                self._reason = "idle timeout"
                return "expired"
