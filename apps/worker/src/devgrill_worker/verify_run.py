"""VerifyRun: one verify of an attempt, as a child of its SandboxLifecycle (ADR 015).

  begin   freeze the incident (stop the load), open the verify_runs row, announce the probes
  probes  one activity per probe group (load probes sharing a replay run together), each
          storing its results and streaming progress as it goes
  finish  decide (passed / partial / failed / error), tell the player, resolve or go back

One activity per group means a crashed worker repeats only the group it was running, and the
run's progress is visible in Temporal as well as in the workspace. Deterministic: no I/O here.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from devgrill_worker.sandbox_activities import (
        ProbeGroupInput,
        SandboxActivities,
        VerifyBegun,
        VerifyFinishInput,
        VerifyInput,
    )

VERIFY_WORKFLOW_NAME = "VerifyRun"
STEP_TIMEOUT = timedelta(minutes=2)
STEP_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=3)
#: A group is one replay (45 s), a chaos window (40 s) or a script: generous, but bounded.
PROBE_TIMEOUT = timedelta(minutes=5)
PROBE_HEARTBEAT = timedelta(minutes=1)
PROBE_RETRY = RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=2)


def verify_workflow_id(attempt_id: str, run: int) -> str:
    return f"verify-{attempt_id}-{run}"


@workflow.defn(name=VERIFY_WORKFLOW_NAME)
class VerifyRun:
    @workflow.run
    async def run(self, inp: VerifyInput) -> bool:
        begun: VerifyBegun = await workflow.execute_activity_method(
            SandboxActivities.verify_begin,
            inp,
            start_to_close_timeout=STEP_TIMEOUT,
            retry_policy=STEP_RETRY,
        )
        error = ""
        try:
            for keys in begun.groups:
                await workflow.execute_activity_method(
                    SandboxActivities.verify_probes,
                    ProbeGroupInput(inp.attempt_id, inp.scenario_slug, begun.run_id, keys),
                    start_to_close_timeout=PROBE_TIMEOUT,
                    heartbeat_timeout=PROBE_HEARTBEAT,
                    retry_policy=PROBE_RETRY,
                )
        except ActivityError as exc:
            # Our side broke (Docker, the probe container): the run is an error, not a fail.
            error = str(exc.cause or exc)[:500]
        return await workflow.execute_activity_method(
            SandboxActivities.verify_finish,
            VerifyFinishInput(
                inp.attempt_id, inp.scenario_slug, begun.run_id, begun.previous_state, error
            ),
            start_to_close_timeout=STEP_TIMEOUT,
            retry_policy=STEP_RETRY,
        )
