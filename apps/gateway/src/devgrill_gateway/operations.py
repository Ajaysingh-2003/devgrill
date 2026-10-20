"""Sandbox operations shared by the workspace (via the API) and the in-sandbox CLI.

Every mutating action (restart, deploy, rollback) is checked against the base app, performed
through the driver, and recorded as an in-world event with its beat trigger, so the timeline,
the war room and later the AI and scoring see the same trail whichever way the player acted.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devgrill.domain.attempt import TERMINAL_STATES
from devgrill.domain.enums import AttemptState
from devgrill.infra.events import EventRecorder
from devgrill.infra.models import Attempt, CodeChange, Scenario, ScenarioVersion
from devgrill.sandbox.compose import LIVE_REF, ComposeDriver, project_name
from devgrill.sandbox.content import Bundle, load_bundle
from devgrill.sandbox.driver import SandboxError, SandboxHandle

log = structlog.get_logger(__name__)

Source = Literal["ui", "cli"]
_SHA = re.compile(r"^[0-9a-f]{4,40}$")
#: States in which the sandbox is up and the player may act on it.
_PLAYABLE = frozenset({AttemptState.ACTIVE, AttemptState.MITIGATED})


class OperationError(Exception):
    """A refused or failed operation, with an HTTP status and a code for the caller."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Sandbox:
    attempt_id: uuid.UUID
    state: AttemptState
    handle: SandboxHandle
    bundle: Bundle
    user_id: uuid.UUID | None
    guest_hash: str | None


class Operations:
    def __init__(
        self,
        *,
        driver: ComposeDriver,
        session_factory: async_sessionmaker[AsyncSession],
        recorder: EventRecorder,
        content_root: Path,
    ) -> None:
        self.driver = driver
        self.session_factory = session_factory
        self.recorder = recorder
        self.content_root = content_root
        self._bundles: dict[str, Bundle] = {}

    # ----------------------------------------------------------------------------- lookup

    async def sandbox(self, attempt_id: uuid.UUID, *, playable: bool = True) -> Sandbox:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(Attempt, Scenario.slug)
                    .join(ScenarioVersion, ScenarioVersion.id == Attempt.scenario_version_id)
                    .join(Scenario, Scenario.id == ScenarioVersion.scenario_id)
                    .where(Attempt.id == attempt_id)
                )
            ).first()
        if row is None:
            raise OperationError(404, "not_found", "No such attempt.")
        attempt, slug = row
        if attempt.state in TERMINAL_STATES:
            raise OperationError(409, "attempt_ended", "This incident has ended.")
        if playable and attempt.state not in _PLAYABLE:
            detail = (
                "The sandbox is still starting."
                if attempt.state is AttemptState.PROVISIONING
                else "The verifier is running; try again when it finishes."
            )
            raise OperationError(409, "sandbox_busy", detail)
        if slug not in self._bundles:
            self._bundles[slug] = load_bundle(self.content_root, slug)
        return Sandbox(
            attempt_id=attempt.id,
            state=attempt.state,
            handle=SandboxHandle(str(attempt.id), project_name(str(attempt.id))),
            bundle=self._bundles[slug],
            user_id=attempt.user_id,
            guest_hash=attempt.guest_token_hash,
        )

    @staticmethod
    def _service(sb: Sandbox, service: str | None, *, patchable: bool = False) -> str:
        app = sb.bundle.base_app
        if service is None:
            if not app.patchable_services:
                raise OperationError(400, "no_source", "Nothing in this system can be deployed.")
            return app.patchable_services[0]
        if service not in app.services or service == app.shell_service:
            raise OperationError(404, "unknown_service", f"There is no service called {service!r}.")
        if patchable and service not in app.patchable_services:
            raise OperationError(400, "not_deployable", f"{service} is not deployed from source.")
        return service

    # ----------------------------------------------------------------------------- read

    async def status(self, attempt_id: uuid.UUID) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        return {"services": await self.driver.status(sb.handle)}

    async def logs(self, attempt_id: uuid.UUID, service: str, tail: int) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service)
        lines = [
            f"{line.ts.isoformat()} {line.line}"
            async for line in self.driver.logs(sb.handle, tail=max(1, min(tail, 1000)))
            if line.service == name
        ]
        return {"service": name, "lines": lines}

    async def files(self, attempt_id: uuid.UUID, service: str | None) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service, patchable=True)
        return {"service": name, "files": await self.driver.list_files(sb.handle, sb.bundle, name)}

    async def read_file(
        self, attempt_id: uuid.UUID, service: str | None, path: str
    ) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service, patchable=True)
        try:
            data = await self.driver.read_file(sb.handle, sb.bundle, name, path)
        except ValueError as exc:
            raise OperationError(400, "bad_path", str(exc)) from exc
        except FileNotFoundError as exc:
            raise OperationError(404, "not_found", f"{path} doesn't exist.") from exc
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OperationError(415, "binary_file", f"{path} isn't a text file.") from exc
        return {"service": name, "path": path, "content": content}

    async def write_file(
        self, attempt_id: uuid.UUID, service: str | None, path: str, content: str
    ) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service, patchable=True)
        try:
            await self.driver.write_file(sb.handle, sb.bundle, name, path, content.encode("utf-8"))
        except ValueError as exc:
            raise OperationError(400, "bad_path", str(exc)) from exc
        except SandboxError as exc:
            raise OperationError(413, "file_too_large", str(exc)) from exc
        return {"service": name, "path": path, "saved": True}

    async def deploys(self, attempt_id: uuid.UUID, service: str | None) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service, patchable=True)
        return await self.driver.deploy_history(sb.handle, sb.bundle, name)

    async def db(self, attempt_id: uuid.UUID) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        try:
            return await self.driver.db_insights(sb.handle, sb.bundle)
        except SandboxError as exc:
            raise OperationError(502, "db_unavailable", str(exc)) from exc

    async def db_query(self, attempt_id: uuid.UUID, sql: str) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        if not sql.strip() or len(sql) > 4000:
            raise OperationError(400, "bad_query", "Queries are 1 to 4000 characters.")
        result = await self.driver.db_query(sb.handle, sb.bundle, sql)
        await self.recorder.record(
            sb.attempt_id, "trail", {"verb": "sql", "query": sql[:500], "ok": "error" not in result}
        )
        return result

    async def cache(self, attempt_id: uuid.UUID) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        try:
            return await self.driver.cache_insights(sb.handle, sb.bundle)
        except SandboxError as exc:
            raise OperationError(502, "cache_unavailable", str(exc)) from exc

    # ----------------------------------------------------------------------------- act

    async def restart(self, attempt_id: uuid.UUID, service: str, source: Source) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service)
        await self.driver.restart(sb.handle, name)
        await self.recorder.record(
            sb.attempt_id,
            "action",
            {"verb": "restart", "service": name, "source": source},
            trigger=f"{name}.restarted",
        )
        return {"message": f"{name} restarted"}

    async def _diff(self, sb: Sandbox, service: str) -> tuple[str, list[str]]:
        """What this deploy changes against what is live (working tree included)."""
        repo = f"/workspace/{service}"
        diff = await self.driver.exec(
            sb.handle, sb.bundle.base_app.shell_service, ["git", "-C", repo, "diff", LIVE_REF]
        )
        names = await self.driver.exec(
            sb.handle,
            sb.bundle.base_app.shell_service,
            ["git", "-C", repo, "diff", "--name-only", LIVE_REF],
        )
        return diff.stdout[:200_000], [n for n in names.stdout.splitlines() if n]

    async def deploy(
        self, attempt_id: uuid.UUID, service: str | None, source: Source
    ) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service, patchable=True)
        diff, files = await self._diff(sb, name)
        change = CodeChange(attempt_id=sb.attempt_id, diff=diff, files=files)
        async with self.session_factory() as session, session.begin():
            session.add(change)
        result = await self.driver.deploy(sb.handle, sb.bundle, name)
        async with self.session_factory() as session, session.begin():
            row = await session.get(CodeChange, change.id)
            if row is not None:
                row.deployed_at = datetime.now(UTC)
                row.deploy_ok = result.ok
        await self.recorder.record(
            sb.attempt_id,
            "deploy",
            {
                "service": name,
                "sha": result.sha,
                "ok": result.ok,
                "message": result.message,
                "files": files,
                "source": source,
            },
            trigger=f"{name}.deployed" if result.ok else None,
        )
        return {
            "ok": result.ok,
            "sha": result.sha,
            "message": result.message,
            "log": result.log[-4000:],
        }

    async def rollback(
        self, attempt_id: uuid.UUID, service: str | None, ref: str, source: Source
    ) -> dict[str, Any]:
        sb = await self.sandbox(attempt_id)
        name = self._service(sb, service, patchable=True)
        if not _SHA.match(ref):
            raise OperationError(
                400, "bad_ref", "Roll back to a commit sha from the deploy history."
            )
        result = await self.driver.deploy(sb.handle, sb.bundle, name, ref=ref)
        await self.recorder.record(
            sb.attempt_id,
            "rollback",
            {"service": name, "ref": ref, "sha": result.sha, "ok": result.ok, "source": source},
            trigger=f"{name}.rolledback" if result.ok else None,
        )
        return {
            "ok": result.ok,
            "sha": result.sha,
            "message": result.message,
            "log": result.log[-4000:],
        }

    async def flags(self, attempt_id: uuid.UUID) -> dict[str, Any]:
        await self.sandbox(attempt_id)
        return {"flags": {}, "message": "This system has no feature flags."}
