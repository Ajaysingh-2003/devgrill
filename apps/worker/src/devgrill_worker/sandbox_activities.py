"""Activities for SandboxLifecycle: everything that touches Docker, the database or Valkey.

Each one is safe to retry: provision starts from a clean slate, state moves to the state an
attempt is already in are no-ops, teardown ignores what is already gone. The sandbox handle
is derived from the attempt id, so teardown works even when provisioning never returned.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
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
from devgrill.infra.repositories import attempts
from devgrill.sandbox.compose import ComposeDriver, project_name
from devgrill.sandbox.content import Bundle, load_bundle
from devgrill.sandbox.driver import SandboxHandle, SandboxSpec
from devgrill.sandbox.lifecycle import LaterFault, LifecycleInput, Provisioned, events_channel
from devgrill.sandbox.verifier import Verifier

log = structlog.get_logger(__name__)

_OUTCOMES = {
    "abandoned": AttemptState.ABANDONED,
    "expired": AttemptState.EXPIRED,
    "failed": AttemptState.FAILED,
    "resolved": AttemptState.RESOLVED,
}


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


def handle_for(attempt_id: str) -> SandboxHandle:
    return SandboxHandle(attempt_id, project_name(attempt_id))


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
        self._load = bundle_loader or (lambda slug: load_bundle(settings.content_root, slug))

    # ---------------------------------------------------------------------- helpers

    @contextlib.asynccontextmanager
    async def _tx(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session, session.begin():
            yield session

    async def _announce(self, attempt_id: str) -> None:
        """Wake SSE listeners; they read the new rows from attempt_events."""
        if self.valkey is None:
            return
        try:
            await self.valkey.publish(events_channel(attempt_id), "1")
        except Exception as exc:
            log.warning("events.publish_failed", attempt_id=attempt_id, error=type(exc).__name__)

    async def _event(self, attempt_id: str, type_: str, payload: dict[str, Any]) -> None:
        async with self._tx() as session:
            await attempts.add_event(session, uuid.UUID(attempt_id), type_, payload)
        await self._announce(attempt_id)

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
        async with self._heartbeating():
            handle = await self.driver.create(
                SandboxSpec(inp.attempt_id, bundle, control_token=uuid.uuid4().hex)
            )
            steps = sorted(bundle.scenario.faults, key=lambda s: s.at_seconds)
            for step in (s for s in steps if s.at_seconds <= 0):
                await self.driver.apply_fault(handle, bundle, step.use, dict(step.params))
            await self.driver.start_load(handle, bundle)
        later = [LaterFault(s.at_seconds, s.use, dict(s.params)) for s in steps if s.at_seconds > 0]
        return Provisioned(handle.ref, later)

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
            await attempts.move(
                session, attempt_id, AttemptState.ACTIVE, expires_at=expires.isoformat()
            )
        await self._announce(inp.attempt_id)
        return provisioned

    @activity.defn(name="sandbox.reset")
    async def reset(self, inp: LifecycleInput) -> Provisioned:
        await self._event(inp.attempt_id, "sandbox", {"action": "reset", "status": "started"})
        provisioned = await self._boot(inp)  # create() destroys the old one first
        await self._event(inp.attempt_id, "sandbox", {"action": "reset", "status": "done"})
        return provisioned

    @activity.defn(name="sandbox.apply_fault")
    async def apply_fault(self, inp: ApplyFaultInput) -> None:
        bundle = self._load(inp.scenario_slug)
        await self.driver.apply_fault(handle_for(inp.attempt_id), bundle, inp.use, dict(inp.params))
        await self._event(
            inp.attempt_id, "fault", {"use": inp.use}
        )  # hidden from players in phase 4

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

    @activity.defn(name="sandbox.verify")
    async def verify(self, inp: LifecycleInput) -> bool:
        attempt_id = uuid.UUID(inp.attempt_id)
        bundle = self._load(inp.scenario_slug)
        handle = handle_for(inp.attempt_id)
        async with self._tx() as session:
            await attempts.move(session, attempt_id, AttemptState.VERIFYING)
        await self._announce(inp.attempt_id)
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
        async with self._tx() as session:
            await attempts.add_event(session, attempt_id, "verify", payload)
            await attempts.move(
                session, attempt_id, AttemptState.RESOLVED if passed else AttemptState.ACTIVE
            )
        await self._announce(inp.attempt_id)
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
        await self._announce(inp.attempt_id)
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
            self.extended,
            self.verify,
            self.teardown,
        ]
