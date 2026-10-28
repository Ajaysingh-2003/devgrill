"""The SandboxDriver protocol (ADR 007) and the values that cross it.

Workflows and the content CLI only ever see these types. Phase 3 ships ComposeDriver
(Docker Engine API); Sysbox, Firecracker or a hosted provider implement the same protocol
later without touching content.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from devgrill.sandbox.content import Bundle


class SandboxError(RuntimeError):
    """The sandbox could not do what was asked (boot, apply, deploy...)."""


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Everything needed to boot one sandbox for one attempt."""

    attempt_id: str
    bundle: Bundle
    #: Secret the in-sandbox `devgrill` CLI presents to the control plane (phase 4).
    control_token: str = ""


@dataclass(frozen=True, slots=True)
class SandboxHandle:
    """Serializable (it crosses Temporal activities); the driver finds everything from it."""

    attempt_id: str
    #: Driver-specific reference (project name, VM id...).
    ref: str


@dataclass(frozen=True, slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True, slots=True)
class DeployResult:
    ok: bool
    sha: str
    message: str
    log: str


@dataclass(frozen=True, slots=True)
class LogLine:
    ts: datetime
    service: str
    line: str


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Raw Prometheus text per job, scraped at `at`."""

    at: datetime
    raw: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    cpu_seconds: float
    memory_bytes: int


class SandboxDriver(Protocol):
    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...
    async def wait_healthy(self, handle: SandboxHandle, timeout_s: int) -> None: ...
    async def apply_fault(
        self, handle: SandboxHandle, bundle: Bundle, use: str, params: dict[str, object]
    ) -> None: ...
    async def revert_fault(
        self, handle: SandboxHandle, bundle: Bundle, use: str, params: dict[str, object]
    ) -> None: ...
    async def start_load(
        self, handle: SandboxHandle, bundle: Bundle, *, multiplier: float = 1.0
    ) -> None: ...
    async def stop_load(self, handle: SandboxHandle) -> None: ...
    async def exec(
        self, handle: SandboxHandle, service: str, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult: ...
    async def probe(
        self, handle: SandboxHandle, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult: ...
    async def deploy(
        self, handle: SandboxHandle, bundle: Bundle, service: str, ref: str | None = None
    ) -> DeployResult: ...
    async def restart(self, handle: SandboxHandle, service: str) -> None: ...
    def logs(
        self, handle: SandboxHandle, *, since: datetime | None = None, tail: int = 200
    ) -> AsyncIterator[LogLine]: ...
    async def metrics(self, handle: SandboxHandle, bundle: Bundle) -> MetricSnapshot: ...
    async def usage(self, handle: SandboxHandle, service: str | None = None) -> ResourceUsage: ...
    async def destroy(self, handle: SandboxHandle) -> None: ...
    async def list_sandboxes(self) -> list[str]: ...
