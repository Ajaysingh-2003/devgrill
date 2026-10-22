"""Workflow definitions. Deterministic only: no I/O, clocks or randomness outside Temporal."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from devgrill_worker.activities import pong

from devgrill_worker.postmortem_review import PostmortemReview
from devgrill_worker.sandbox_lifecycle import SandboxLifecycle
from devgrill_worker.verify_run import VerifyRun


@workflow.defn
class PingWorkflow:
    """Smoke-test workflow: proves server, worker and activity wiring end to end."""

    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            pong, name, start_to_close_timeout=timedelta(seconds=10)
        )


WORKFLOWS = [PingWorkflow, SandboxLifecycle, VerifyRun, PostmortemReview]
#: Plain activities; the sandbox and AI ones are bound to their dependencies in __main__.
ACTIVITIES = [pong]
