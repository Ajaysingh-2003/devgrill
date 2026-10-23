"""SandboxLifecycle: one workflow per attempt, from provisioning to guaranteed teardown.

  provision (boot, faults due before T, load, the page)  ->  active
  active:  the monitor activity samples metrics and reports health changes
           timers: faults and teammate beats due after T, the TTL, the idle timeout
           signals: abandon, reset, extend, verify, touch (player activity), health
  health:  active -> mitigated when the SLO holds again after the breach;
           mitigated -> active when it breaks again (regressed)
  verify:  a VerifyRun child workflow (ADR 015); passing resolves the incident
  finally: teardown (measure, destroy, close the session, settle the attempt's state),
           then settle the result (score, approach, ratings), then the AI's reading of it
           (coach note, unrecognised approach; ADR 016), best effort

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
        SIGNAL_HEALTH,
        SIGNAL_RESET,
        SIGNAL_TOUCH,
        SIGNAL_VERIFY,
        WORKFLOW_NAME,
        LaterFault,
        LifecycleInput,
        LifecycleStatus,
        Provisioned,
        TimedBeat,
    )
    from devgrill_worker.ai_activities import AiActivities
    from devgrill_worker.sandbox_activities import (
        ApplyFaultInput,
        BeatInput,
        ExtendInput,
        SandboxActivities,
        SetStateInput,
        SettleInput,
        TeardownInput,
        VerifyInput,
    )
    from devgrill_worker.verify_run import VerifyRun, verify_workflow_id

PROVISION_TIMEOUT = timedelta(minutes=5)
PROVISION_HEARTBEAT = timedelta(seconds=30)
PROVISION_RETRY = RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=3)
STEP_TIMEOUT = timedelta(minutes=3)
STEP_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3)
#: A verify run must finish within this (its probes are bounded well inside it).
VERIFY_TIMEOUT = timedelta(minutes=15)
MONITOR_HEARTBEAT = timedelta(seconds=30)
# The monitor keeps sampling through hiccups (Docker busy, a worker restart).
MONITOR_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2), maximum_interval=timedelta(seconds=30)
)
# Teardown retries until Docker answers again (bounded by its schedule-to-close).
TEARDOWN_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2), maximum_interval=timedelta(minutes=1)
)
TEARDOWN_DEADLINE = timedelta(hours=2)
#: The coach note and classification: two judge calls and a couple of embeddings.
REVIEW_TIMEOUT = timedelta(minutes=4)
REVIEW_RETRY = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=2)


@workflow.defn(name=WORKFLOW_NAME)
class SandboxLifecycle:
    def __init__(self) -> None:
        self._state = "provisioning"
        self._abandon = False
        self._reset = False
        self._verify = False
        self._extend_requests = 0
        self._touched = False
        self._health: list[bool] = []
        self._expires_at: datetime | None = None
        self._extends_used = 0
        self._resets_used = 0
        self._verify_runs = 0
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

    @workflow.signal(name=SIGNAL_HEALTH)
    def health(self, healthy: bool) -> None:
        self._health.append(healthy)

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
            # The result is settled once the sandbox is gone; a failure here is logged by
            # Temporal and never undoes the teardown.
            try:
                await workflow.execute_activity_method(
                    SandboxActivities.settle,
                    SettleInput(inp.attempt_id, inp.scenario_slug),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )
            except ActivityError:
                workflow.logger.warning(
                    "settling the attempt failed", extra={"attempt_id": inp.attempt_id}
                )
            else:
                try:
                    await workflow.execute_activity_method(
                        AiActivities.review,
                        inp.attempt_id,
                        start_to_close_timeout=REVIEW_TIMEOUT,
                        retry_policy=REVIEW_RETRY,
                    )
                except ActivityError:
                    workflow.logger.warning(
                        "the AI review of the attempt failed", extra={"attempt_id": inp.attempt_id}
                    )
        return outcome

    async def _set_state(self, inp: LifecycleInput, state: str, reason: str = "") -> None:
        await workflow.execute_activity_method(
            SandboxActivities.set_state,
            SetStateInput(inp.attempt_id, state, reason),
            start_to_close_timeout=STEP_TIMEOUT,
            retry_policy=STEP_RETRY,
        )
        self._state = state

    async def _play(self, inp: LifecycleInput, provisioned: Provisioned) -> str:
        self._state = "active"
        lifetime = timedelta(minutes=inp.ttl_minutes + inp.max_extends * inp.extend_minutes + 10)
        monitor = workflow.start_activity_method(
            SandboxActivities.monitor,
            inp,
            start_to_close_timeout=lifetime,
            heartbeat_timeout=MONITOR_HEARTBEAT,
            retry_policy=MONITOR_RETRY,
        )
        try:
            return await self._loop(inp, provisioned)
        finally:
            monitor.cancel()
            with contextlib.suppress(BaseException):
                await monitor

    async def _loop(self, inp: LifecycleInput, provisioned: Provisioned) -> str:
        start = workflow.now()
        deadline = start + timedelta(minutes=inp.ttl_minutes)
        idle = timedelta(minutes=inp.idle_minutes)
        idle_deadline = start + idle
        self._expires_at = deadline
        faults: list[LaterFault] = sorted(provisioned.later_faults, key=lambda f: f.at_seconds)
        beats: list[TimedBeat] = sorted(
            provisioned.timed_beats, key=lambda b: (b.at_seconds, b.index)
        )

        while True:
            now = workflow.now()
            due = [
                deadline,
                idle_deadline,
                *(start + timedelta(seconds=f.at_seconds) for f in faults[:1]),
                *(start + timedelta(seconds=b.at_seconds) for b in beats[:1]),
            ]
            with contextlib.suppress(TimeoutError):
                await workflow.wait_condition(
                    lambda: (
                        self._abandon
                        or self._reset
                        or self._verify
                        or self._touched
                        or self._extend_requests > 0
                        or bool(self._health)
                    ),
                    timeout=max(min(due) - now, timedelta(0)),
                )
            now = workflow.now()

            if self._abandon:
                self._reason = "abandoned by the player"
                return "abandoned"
            if self._touched:
                self._touched = False
                idle_deadline = now + idle
            while self._health:
                healthy = self._health.pop(0)
                if healthy and self._state == "active":
                    await self._set_state(
                        inp, "mitigated", "the service is meeting its target again"
                    )
                elif not healthy and self._state == "mitigated":
                    await self._set_state(inp, "active", "the service went over its target again")
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
                    self._health.clear()  # reports about the old sandbox mean nothing now
                    # The incident restarts; the session's deadline does not. Beats that
                    # already fired don't fire again (the recorder checks).
                    start = workflow.now()
                    faults = sorted(provisioned.later_faults, key=lambda f: f.at_seconds)
                    idle_deadline = start + idle
            if self._verify:
                previous = self._state
                self._state = "verifying"
                self._verify_runs += 1
                passed: bool = await workflow.execute_child_workflow(
                    VerifyRun.run,
                    VerifyInput(inp.attempt_id, inp.scenario_slug, self._verify_runs),
                    id=verify_workflow_id(inp.attempt_id, self._verify_runs),
                    execution_timeout=VERIFY_TIMEOUT,
                )
                # Requests that arrived while verifying are answered by this run.
                self._verify = False
                if passed:
                    return "resolved"
                self._state = previous  # the run moved the attempt back too
                idle_deadline = workflow.now() + idle
            now = workflow.now()
            while faults and start + timedelta(seconds=faults[0].at_seconds) <= now:
                fault = faults.pop(0)
                await workflow.execute_activity_method(
                    SandboxActivities.apply_fault,
                    ApplyFaultInput(inp.attempt_id, inp.scenario_slug, fault.use, fault.params),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )
            while beats and start + timedelta(seconds=beats[0].at_seconds) <= now:
                beat = beats.pop(0)
                await workflow.execute_activity_method(
                    SandboxActivities.beat,
                    BeatInput(inp.attempt_id, beat.index),
                    start_to_close_timeout=STEP_TIMEOUT,
                    retry_policy=STEP_RETRY,
                )
            if now >= deadline:
                self._reason = "time limit reached"
                return "expired"
            if now >= idle_deadline:
                self._reason = "idle timeout"
                return "expired"
