"""Activities for SandboxLifecycle: everything that touches Docker, the database or Valkey.

Each one is safe to retry: provision starts from a clean slate, state moves to the state an
attempt is already in are no-ops, beats fire once, teardown ignores what is already gone. The
sandbox handle is derived from the attempt id, so teardown works even when provisioning never
returned.

In-world events (boot steps, the page, state changes and the beats they trigger, timed beats)
go through `EventRecorder`, which also wakes the SSE stream. The monitor samples metrics for
the workspace's charts and tells the workflow when the service is healthy again (mitigated)
or breaks again (regressed).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from devgrill.config import Settings
from devgrill.domain.attempt import can_transition
from devgrill.domain.enums import AttemptState, SandboxDriver
from devgrill.domain.events import state_trigger, timed_beats
from devgrill.infra.events import EventRecorder, fire_trigger
from devgrill.infra.repositories import attempts
from devgrill.sandbox.compose import ComposeDriver, project_name
from devgrill.sandbox.content import Bundle, load_bundle
from devgrill.sandbox.driver import SandboxError, SandboxHandle, SandboxSpec
from devgrill.sandbox.lifecycle import (
    HISTORY_SAMPLES,
    SAMPLE_EVERY_S,
    SIGNAL_HEALTH,
    LaterFault,
    LifecycleInput,
    Provisioned,
    TimedBeat,
    samples_key,
    telemetry_channel,
    workflow_id,
)
from devgrill.sandbox.metrics import Scrape, evaluate_all, parse_text
from devgrill.sandbox.verifier import Verifier

log = structlog.get_logger(__name__)

_OUTCOMES = {
    "abandoned": AttemptState.ABANDONED,
    "expired": AttemptState.EXPIRED,
    "failed": AttemptState.FAILED,
    "resolved": AttemptState.RESOLVED,
}
#: Rates and quantiles are computed over this many samples (10 s at 2 s): smooth, still quick.
WINDOW_SAMPLES = 5
#: A mitigated service that stays unhealthy this long has regressed.
REGRESS_AFTER_S = 20.0


@dataclass(slots=True)
class ApplyFaultInput:
    attempt_id: str
    scenario_slug: str
    use: str
    params: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ExtendInput:
    attempt_id: str
    granted: bool
    expires_at: str


@dataclass(slots=True)
class TeardownInput:
    attempt_id: str
    outcome: str
    reason: str = ""


@dataclass(slots=True)
class SetStateInput:
    attempt_id: str
    state: str
    reason: str = ""


@dataclass(slots=True)
class BeatInput:
    attempt_id: str
    index: int


def handle_for(attempt_id: str) -> SandboxHandle:
    return SandboxHandle(attempt_id, project_name(attempt_id))


class HealthTracker:
    """Breached-then-recovered detection, from per-sample SLO checks (pure; unit-tested).

    - Mitigated: the SLO was breached at least once, then held for `hold_s`.
    - Regressed: after mitigation, the SLO failed continuously for `regress_s`.
    Samples where a target can't be measured (no traffic) change nothing.
    """

    def __init__(self, hold_s: float, regress_s: float = REGRESS_AFTER_S) -> None:
        self.hold_s = hold_s
        self.regress_s = regress_s
        self.breached = False
        self.mitigated = False
        self._healthy_since: float | None = None
        self._unhealthy_since: float | None = None

    def observe(self, healthy: bool | None, now: float) -> bool | None:
        """Feed one sample; returns True (mitigated), False (regressed) or None (no change)."""
        if healthy is None:
            return None
        if healthy:
            self._unhealthy_since = None
            if self._healthy_since is None:
                self._healthy_since = now
            if self.breached and not self.mitigated and now - self._healthy_since >= self.hold_s:
                self.mitigated = True
                return True
            return None
        self.breached = True
        self._healthy_since = None
        if self._unhealthy_since is None:
            self._unhealthy_since = now
        if self.mitigated and now - self._unhealthy_since >= self.regress_s:
            self.mitigated = False
            return False
        return None


class SandboxActivities:
    def __init__(
        self,
        *,
        settings: Settings,
        driver: ComposeDriver,
        session_factory: async_sessionmaker[AsyncSession],
        valkey: Redis | None,
        bundle_loader: Callable[[str], Bundle] | None = None,
    ) -> None:
        self.settings = settings
        self.driver = driver
        self.session_factory = session_factory
        self.valkey = valkey
        self.recorder = EventRecorder(session_factory, valkey)
        self._load = bundle_loader or (lambda slug: load_bundle(settings.content_root, slug))

    # ---------------------------------------------------------------------- helpers

    @contextlib.asynccontextmanager
    async def _tx(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session, session.begin():
            yield session

    async def _event(self, attempt_id: str, type_: str, payload: dict[str, Any]) -> None:
        await self.recorder.record(uuid.UUID(attempt_id), type_, payload)

    async def _move(self, attempt_id: str, target: AttemptState, **payload: Any) -> None:
        """Move the attempt, fire the beats the new state triggers, wake the SSE stream."""
        async with self._tx() as session:
            attempt = await attempts.get(session, uuid.UUID(attempt_id))
            if (
                attempt is None
                or attempt.state is target
                or not can_transition(attempt.state, target)
            ):
                return
            await attempts.move(session, attempt.id, target, **payload)
            await fire_trigger(session, attempt.id, state_trigger(target.value))
        await self.recorder.announce(attempt_id)

    @contextlib.asynccontextmanager
    async def _heartbeating(self, every_s: float = 10) -> AsyncIterator[None]:
        async def beat() -> None:
            while True:
                activity.heartbeat()
                await asyncio.sleep(every_s)

        task = asyncio.create_task(beat())
        try:
            yield
        finally:
            task.cancel()

    async def _boot(self, inp: LifecycleInput) -> Provisioned:
        bundle = self._load(inp.scenario_slug)

        async def step(name: str) -> None:
            await self._event(inp.attempt_id, "boot", {"step": name})

        async with self._heartbeating():
            await step("sandbox")
            spec = SandboxSpec(inp.attempt_id, bundle, control_token=uuid.uuid4().hex)
            handle = await self.driver.create(spec, progress=step)
            steps = sorted(bundle.scenario.faults, key=lambda s: s.at_seconds)
            await step("history")
            for fault in (s for s in steps if s.at_seconds <= 0):
                await self.driver.apply_fault(handle, bundle, fault.use, dict(fault.params))
            await step("traffic")
            await self.driver.start_load(handle, bundle)
        later = [LaterFault(s.at_seconds, s.use, dict(s.params)) for s in steps if s.at_seconds > 0]
        beats = [TimedBeat(at, index) for at, index, _ in timed_beats(bundle.scenario.beats)]
        return Provisioned(handle.ref, later, beats)

    # -------------------------------------------------------------------- activities

    @activity.defn(name="sandbox.provision")
    async def provision(self, inp: LifecycleInput) -> Provisioned:
        attempt_id = uuid.UUID(inp.attempt_id)
        expires = datetime.now(UTC) + timedelta(minutes=inp.ttl_minutes)
        async with self._tx() as session:
            await attempts.open_session(
                session,
                attempt_id=attempt_id,
                driver=SandboxDriver.COMPOSE,
                external_ref=project_name(inp.attempt_id),
                resources={
                    "tier": inp.tier,
                    "ttl_minutes": inp.ttl_minutes,
                    "idle_minutes": inp.idle_minutes,
                },
                expires_at=expires,
            )
        provisioned = await self._boot(inp)
        # The clock starts when the player can act, not when we started booting.
        expires = datetime.now(UTC) + timedelta(minutes=inp.ttl_minutes)
        async with self._tx() as session:
            await attempts.mark_ready(session, attempt_id, expires)
        bundle = self._load(inp.scenario_slug)
        if bundle.scenario.page is not None:
            page = bundle.scenario.page
            await self._event(
                inp.attempt_id, "alert", {"severity": page.severity, "title": page.title}
            )
        await self._move(inp.attempt_id, AttemptState.ACTIVE, expires_at=expires.isoformat())
        return provisioned

    @activity.defn(name="sandbox.reset")
    async def reset(self, inp: LifecycleInput) -> Provisioned:
        await self._event(inp.attempt_id, "sandbox", {"action": "reset", "status": "started"})
        provisioned = await self._boot(inp)  # create() destroys the old one first
        async with self._tx() as session:
            # The SLO starts broken again: back to investigating.
            attempt = await attempts.get(session, uuid.UUID(inp.attempt_id))
            if attempt is not None and attempt.state is AttemptState.MITIGATED:
                await attempts.move(session, attempt.id, AttemptState.ACTIVE, reason="reset")
        await self._event(inp.attempt_id, "sandbox", {"action": "reset", "status": "done"})
        return provisioned

    @activity.defn(name="sandbox.apply_fault")
    async def apply_fault(self, inp: ApplyFaultInput) -> None:
        bundle = self._load(inp.scenario_slug)
        await self.driver.apply_fault(handle_for(inp.attempt_id), bundle, inp.use, dict(inp.params))
        await self._event(inp.attempt_id, "fault", {"use": inp.use})  # hidden from players

    @activity.defn(name="sandbox.set_state")
    async def set_state(self, inp: SetStateInput) -> None:
        await self._move(inp.attempt_id, AttemptState(inp.state), reason=inp.reason)

    @activity.defn(name="sandbox.beat")
    async def beat(self, inp: BeatInput) -> None:
        await self.recorder.beat(uuid.UUID(inp.attempt_id), inp.index)

    @activity.defn(name="sandbox.extended")
    async def extended(self, inp: ExtendInput) -> None:
        if inp.granted:
            async with self._tx() as session:
                await attempts.set_expiry(
                    session, uuid.UUID(inp.attempt_id), datetime.fromisoformat(inp.expires_at)
                )
        await self._event(
            inp.attempt_id, "extend", {"granted": inp.granted, "expires_at": inp.expires_at}
        )

    @activity.defn(name="sandbox.monitor")
    async def monitor(self, inp: LifecycleInput) -> None:
        """Sample metrics every 2 s until cancelled: charts, history, mitigation detection."""
        bundle = self._load(inp.scenario_slug)
        handle = handle_for(inp.attempt_id)
        slo = bundle.scenario.slo
        tracker = HealthTracker(hold_s=slo.for_s if slo else 60)
        window: deque[Scrape] = deque(maxlen=WINDOW_SAMPLES + 1)
        workflow = activity.client().get_workflow_handle(workflow_id(inp.attempt_id))
        key, channel = samples_key(inp.attempt_id), telemetry_channel(inp.attempt_id)
        while True:
            started = time.monotonic()
            activity.heartbeat()
            try:
                snapshot = await self.driver.metrics(handle, bundle)
            except (SandboxError, OSError) as exc:  # a reset or restart in progress
                log.info("monitor.scrape_failed", attempt_id=inp.attempt_id, error=str(exc)[:200])
                await asyncio.sleep(SAMPLE_EVERY_S)
                continue
            window.append(
                Scrape(started, {job: parse_text(text) for job, text in snapshot.raw.items()})
            )
            values = evaluate_all(
                bundle.base_app.metrics, window[0] if len(window) > 1 else None, window[-1]
            )
            sample = {
                "t": round(time.time(), 3),
                "values": {k: (round(v, 4) if v is not None else None) for k, v in values.items()},
            }
            if self.valkey is not None:
                payload = json.dumps(sample)
                pipe = self.valkey.pipeline()
                pipe.lpush(key, payload)
                pipe.ltrim(key, 0, HISTORY_SAMPLES - 1)
                pipe.expire(key, 24 * 3600)
                pipe.publish(channel, payload)
                await pipe.execute()
            if slo is not None:
                change = tracker.observe(_slo_healthy(slo.targets(), values), started)
                if change is not None:
                    await self._event(
                        inp.attempt_id, "health", {"healthy": change, "values": sample["values"]}
                    )
                    await workflow.signal(SIGNAL_HEALTH, change)
            await asyncio.sleep(max(0.0, SAMPLE_EVERY_S - (time.monotonic() - started)))

    @activity.defn(name="sandbox.verify")
    async def verify(self, inp: LifecycleInput) -> bool:
        attempt_id = uuid.UUID(inp.attempt_id)
        bundle = self._load(inp.scenario_slug)
        handle = handle_for(inp.attempt_id)
        async with self._tx() as session:
            current = await attempts.get(session, attempt_id)
            previous = current.state if current is not None else AttemptState.ACTIVE
        await self._move(inp.attempt_id, AttemptState.VERIFYING)
        async with self._heartbeating(30):
            await self.driver.stop_load(handle)
            results = await Verifier(self.driver, handle, bundle).run_all(bundle.scenario.probes)
        passed = bool(results) and all(r.passed for r in results)
        payload = {
            "passed": passed,
            "probes": [
                {
                    "key": r.key,
                    "title": r.title,
                    "passed": r.passed,
                    "detail": r.detail,
                    "measured": r.measured,
                }
                for r in results
            ],
        }
        await self.recorder.record(attempt_id, "verify", payload)
        # A failed verify returns to where the player was (still mitigated, or not yet).
        back = (
            previous
            if previous in (AttemptState.ACTIVE, AttemptState.MITIGATED)
            else AttemptState.ACTIVE
        )
        await self._move(inp.attempt_id, AttemptState.RESOLVED if passed else back)
        if not passed:
            await self.driver.start_load(handle, bundle)  # back to the incident
        return passed

    @activity.defn(name="sandbox.teardown")
    async def teardown(self, inp: TeardownInput) -> None:
        attempt_id = uuid.UUID(inp.attempt_id)
        handle = handle_for(inp.attempt_id)
        cpu_seconds: float | None = None
        with contextlib.suppress(Exception):  # usage is best effort; destroy is not
            cpu_seconds = (await self.driver.usage(handle)).cpu_seconds
        await self.driver.destroy(handle)
        async with self._tx() as session:
            await attempts.close_session(
                session,
                attempt_id,
                cpu_seconds=cpu_seconds,
                cost_per_hour_usd=self.settings.sandbox_cost_per_hour_usd,
            )
            attempt = await attempts.get(session, attempt_id)
            target = _OUTCOMES.get(inp.outcome, AttemptState.FAILED)
            if (
                attempt is not None
                and attempt.state is not target
                and can_transition(attempt.state, target)
            ):
                await attempts.move(session, attempt_id, target, reason=inp.reason)
            await attempts.add_event(
                session, attempt_id, "sandbox", {"action": "destroyed", "reason": inp.reason}
            )
        await self.recorder.announce(inp.attempt_id)
        # The sample history stays (it expires by itself): the debrief charts it.
        log.info(
            "sandbox.teardown",
            attempt_id=inp.attempt_id,
            outcome=inp.outcome,
            cpu_seconds=cpu_seconds,
        )

    def all(self) -> list[Callable[..., Any]]:
        return [
            self.provision,
            self.reset,
            self.apply_fault,
            self.set_state,
            self.beat,
            self.extended,
            self.monitor,
            self.verify,
            self.teardown,
        ]


def _slo_healthy(targets: dict[str, Any], values: dict[str, float | None]) -> bool | None:
    """True/False when every target is measurable; None when one isn't (no traffic yet)."""
    for metric, target in targets.items():
        value = values.get(metric)
        if value is None:
            return None
        if not target.holds(value):
            return False
    return True
