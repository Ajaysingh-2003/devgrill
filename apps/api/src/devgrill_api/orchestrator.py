"""How the API starts and steers attempts (the SandboxLifecycle workflow) and asks for
postmortem reviews (the PostmortemReview workflow), behind a port.

Tests swap in a fake (`app.state.orchestrator`) so the attempt endpoints run without Temporal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.service import RPCError

from devgrill.infra.assist import REVIEW_WORKFLOW, review_workflow_id
from devgrill.infra.workflows import connect_temporal
from devgrill.sandbox.lifecycle import WORKFLOW_NAME, LifecycleInput, workflow_id

if TYPE_CHECKING:
    from devgrill.config import Settings


class OrchestratorError(RuntimeError):
    """The workflow engine is unreachable or refused the request."""


class Orchestrator(Protocol):
    async def start(self, inp: LifecycleInput) -> None: ...
    async def signal(self, attempt_id: str, name: str) -> None: ...
    async def review(self, attempt_id: str) -> None: ...


class TemporalOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Client | None = None

    async def _connect(self) -> Client:
        if self._client is None:
            try:
                self._client = await connect_temporal(self._settings)
            except (RPCError, RuntimeError, OSError) as exc:
                raise OrchestratorError(f"temporal unreachable: {exc}") from exc
        return self._client

    async def start(self, inp: LifecycleInput) -> None:
        client = await self._connect()
        try:
            await client.start_workflow(
                WORKFLOW_NAME,
                inp,
                id=workflow_id(inp.attempt_id),
                task_queue=self._settings.temporal_task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except RPCError as exc:
            raise OrchestratorError(str(exc)) from exc

    async def signal(self, attempt_id: str, name: str) -> None:
        client = await self._connect()
        try:
            await client.get_workflow_handle(workflow_id(attempt_id)).signal(name)
        except RPCError as exc:
            raise OrchestratorError(str(exc)) from exc

    async def review(self, attempt_id: str) -> None:
        """Grade the attempt's submitted postmortem (a run already in progress is reused)."""
        client = await self._connect()
        try:
            await client.start_workflow(
                REVIEW_WORKFLOW,
                attempt_id,
                id=review_workflow_id(attempt_id),
                task_queue=self._settings.temporal_task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            )
        except RPCError as exc:
            raise OrchestratorError(str(exc)) from exc
