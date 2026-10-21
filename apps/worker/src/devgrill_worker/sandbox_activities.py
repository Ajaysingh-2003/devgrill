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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from devgrill.config import Settings
from devgrill.domain.attempt import can_transition
from devgrill.domain.enums import AttemptState, SandboxDriver, VerifyStatus
from devgrill.domain.events import state_trigger, timed_beats
from devgrill.infra.events import EventRecorder, fire_trigger
from devgrill.infra.models import Attempt, Probe, ProbeResult, VerifyRun
from devgrill.infra.objectstore import ObjectStore, ObjectStoreError
from devgrill.infra.repositories import attempts
from devgrill.infra.settle import settle
from devgrill.sandbox.compose import ComposeDriver, project_name
from devgrill.sandbox.content import Bundle, load_approaches, load_bundle
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
from devgrill.sandbox.verifier import Verifier, plan

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


@dataclass(slots=True)
class VerifyInput:
    attempt_id: str
    scenario_slug: str
    #: 1, 2, ... per attempt: the run's id is derived from it, so a retried begin is a no-op.
    run: int


@dataclass(slots=True)
class VerifyBegun:
    run_id: str
    previous_state: str
    #: Probe keys per activity (load probes sharing a replay go together).
    groups: list[list[str]] = field(default_factory=list)


@dataclass(slots=True)
class ProbeGroupInput:
    attempt_id: str
    scenario_slug: str
    run_id: str
    keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerifyFinishInput:
    attempt_id: str
    scenario_slug: str
    run_id: str
    previous_state: str
    error: str = ""


@dataclass(slots=True)
class SettleInput:
    attempt_id: str
    scenario_slug: str


def verify_run_id(attempt_id: str, run: int) -> uuid.UUID:
    return uuid.uuid5(uuid.UUID(attempt_id), f"verify-{run}")


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
        store: ObjectStore | None = None,
    ) -> None:
        self.settings = settings
        self.driver = driver
        self.session_factory = session_factory
        self.valkey = valkey
        self.store = store
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

    # ------------------------------------------------------------------- verify (ADR 015)

    @activity.defn(name="verify.begin")
    async def verify_begin(self, inp: VerifyInput) -> VerifyBegun:
        """Freeze the incident (no load), open the run, announce the probes it will run."""
        attempt_id = uuid.UUID(inp.attempt_id)
        bundle = self._load(inp.scenario_slug)
        run_id = verify_run_id(inp.attempt_id, inp.run)
        async with self._tx() as session:
            existing = await session.get(VerifyRun, run_id)
            if existing is not None:  # a retried begin: keep the first answer
                previous = AttemptState((existing.summary or {}).get("previous_state", "active"))
            else:
                current = await attempts.get(session, attempt_id)
                previous = current.state if current is not None else AttemptState.ACTIVE
                session.add(
                    VerifyRun(
                        id=run_id,
                        attempt_id=attempt_id,
                        status=VerifyStatus.RUNNING,
                        started_at=datetime.now(UTC),
                        summary={
                            "run": inp.run,
                            "previous_state": previous.value,
                            "probes": [
                                {
                                    "key": p.key,
                                    "kind": p.kind.value,
                                    "title": p.title,
                                    "how": p.how,
                                    "weight": p.weight,
                                    "status": "queued",
                                }
                                for p in bundle.scenario.probes
                            ],
                        },
                    )
                )
        await self._move(inp.attempt_id, AttemptState.VERIFYING)
        await self.driver.stop_load(handle_for(inp.attempt_id))
        await self._event(
            inp.attempt_id,
            "verify_progress",
            {
                "run_id": str(run_id),
                "status": "started",
                "probes": [{"key": p.key, "title": p.title} for p in bundle.scenario.probes],
            },
        )
        groups = [[p.key for p in group] for group in plan(list(bundle.scenario.probes))]
        return VerifyBegun(str(run_id), previous.value, groups)

    @activity.defn(name="verify.probes")
    async def verify_probes(self, inp: ProbeGroupInput) -> None:
        """Run one group of probes; store each result (and its artifact) as it lands."""
        bundle = self._load(inp.scenario_slug)
        handle = handle_for(inp.attempt_id)
        wanted = [p for p in bundle.scenario.probes if p.key in inp.keys]
        run_id = uuid.UUID(inp.run_id)

        async def progress(key: str, status: str) -> None:
            await self._event(
                inp.attempt_id,
                "verify_progress",
                {"run_id": inp.run_id, "key": key, "status": status},
            )

        async with self._heartbeating(15):
            results = await Verifier(self.driver, handle, bundle).run_group(wanted, progress)
        artifacts: dict[str, str] = {}
        if self.store is not None:
            for r in results:
                key = f"verify/{inp.attempt_id}/{inp.run_id}/{r.key}.json"
                body = json.dumps(
                    {"key": r.key, "passed": r.passed, "measured": r.measured, "detail": r.detail}
                ).encode()
                with contextlib.suppress(ObjectStoreError, OSError):
                    await self.store.put(key, body)
                    artifacts[r.key] = key
        by_key = {r.key: r for r in results}
        async with self._tx() as session:
            run = await session.get(VerifyRun, run_id, with_for_update=True)
            if run is None:
                raise SandboxError(f"verify run {run_id} is missing")
            summary = dict(run.summary or {})
            merged: list[dict[str, Any]] = []
            for p in summary.get("probes", []):
                r = by_key.get(p["key"])
                if r is not None:
                    p = {
                        **p,
                        "status": "passed" if r.passed else "failed",
                        "passed": r.passed,
                        "measured": r.measured,
                        "detail": r.detail,
                        "seconds": r.seconds,
                    }
                merged.append(p)
            run.summary = {**summary, "probes": merged}
            rows = await session.execute(
                select(Probe.key, Probe.id)
                .join(Attempt, Attempt.scenario_version_id == Probe.scenario_version_id)
                .where(Attempt.id == run.attempt_id, Probe.key.in_(list(by_key)))
            )
            # Not dict(rows): a Result has .keys() (its columns), so dict() would index it.
            probe_ids = {key: probe_id for key, probe_id in rows.tuples()}
            for r in results:
                probe_id = probe_ids.get(r.key)
                if probe_id is None:
                    continue  # a version seeded before probes were stored: the summary has it
                row = await session.get(ProbeResult, (run_id, probe_id))
                if row is None:
                    row = ProbeResult(verify_run_id=run_id, probe_id=probe_id)
                    session.add(row)
                row.passed = r.passed
                row.observed = {"measured": r.measured, "detail": r.detail}
                row.artifact_key = artifacts.get(r.key)

    @activity.defn(name="verify.finish")
    async def verify_finish(self, inp: VerifyFinishInput) -> bool:
        """Decide the run, tell the player, and either resolve or go back to the incident."""
        run_id = uuid.UUID(inp.run_id)
        async with self._tx() as session:
            run = await session.get(VerifyRun, run_id, with_for_update=True)
            if run is None:
                raise SandboxError(f"verify run {run_id} is missing")
            summary = dict(run.summary or {})
            probes: list[dict[str, Any]] = list(summary.get("probes", []))
            complete = bool(probes) and all("passed" in p for p in probes)
            passed = complete and not inp.error and all(p["passed"] for p in probes)
            if inp.error or not complete:
                status = VerifyStatus.ERROR
            elif passed:
                status = VerifyStatus.PASSED
            elif any(p.get("passed") for p in probes):
                status = VerifyStatus.PARTIAL
            else:
                status = VerifyStatus.FAILED
            if inp.error:
                summary["error"] = inp.error
            run.summary, run.status, run.finished_at = summary, status, datetime.now(UTC)
        payload: dict[str, Any] = {
            "run_id": inp.run_id,
            "passed": passed,
            "status": status.value,
            "probes": [
                {
                    "key": p["key"],
                    "title": p.get("title"),
                    "how": p.get("how"),
                    "passed": p.get("passed"),  # None: not run
                    "detail": p.get("detail", ""),
                    "measured": p.get("measured", {}),
                }
                for p in probes
            ],
        }
        if inp.error:
            payload["error"] = "Verify couldn't finish on our side; this run doesn't count."
        await self.recorder.record(uuid.UUID(inp.attempt_id), "verify", payload)
        # A failed verify returns to where the player was (still mitigated, or not yet).
        previous = AttemptState(inp.previous_state)
        back = (
            previous
            if previous in (AttemptState.ACTIVE, AttemptState.MITIGATED)
            else AttemptState.ACTIVE
        )
        await self._move(inp.attempt_id, AttemptState.RESOLVED if passed else back)
        if not passed:
            bundle = self._load(inp.scenario_slug)
            await self.driver.start_load(handle_for(inp.attempt_id), bundle)  # back to it
        return passed

    @activity.defn(name="attempt.settle")
    async def settle(self, inp: SettleInput) -> None:
        """Score, approach and ratings, once the attempt has ended (idempotent)."""
        rules = []
        try:
            bundle = self._load(inp.scenario_slug)
            rules = [(s.key, s.match) for _, s in load_approaches(bundle) if not s.cheat]
        except (OSError, ValueError) as exc:  # no content here: score without an approach
            log.warning("settle.no_approaches", attempt_id=inp.attempt_id, error=str(exc)[:200])
        async with self._tx() as session:
            await settle(session, uuid.UUID(inp.attempt_id), approach_rules=rules)
        await self.recorder.announce(inp.attempt_id)

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
            self.verify_begin,
            self.verify_probes,
            self.verify_finish,
            self.teardown,
            self.settle,
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
