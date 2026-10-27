"""The hourly digest sweep (Temporal schedule): sends each opted-in player's daily email in
their own send hour (devgrill.infra.digests has the rules and the once-a-day claim)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from temporalio import activity, workflow
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
)
from temporalio.common import RetryPolicy

# Activity-side code: kept out of the workflow sandbox.
with workflow.unsafe.imports_passed_through():
    import structlog
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from devgrill.infra import digests
    from devgrill.infra.mail import Mailer

log = structlog.get_logger(__name__)

SWEEP_WORKFLOW = "DigestSweep"
SWEEP_SCHEDULE = "digest-sweep"
#: Five past every hour (UTC): every local send hour gets a sweep, whatever the time zone.
SWEEP_CRON = "5 * * * *"


class DigestActivities:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mailer: Mailer,
        links: digests.Links,
    ) -> None:
        self.session_factory, self.mailer, self.links = session_factory, mailer, links

    @activity.defn(name="digests.send_due")
    async def send_due(self) -> int:
        return await digests.send_due(
            self.session_factory, self.mailer, self.links, datetime.now(UTC)
        )


@workflow.defn(name=SWEEP_WORKFLOW)
class DigestSweep:
    @workflow.run
    async def run(self) -> int:
        # Retries are safe: a digest already claimed today is skipped.
        return await workflow.execute_activity_method(
            DigestActivities.send_due,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=30), maximum_attempts=3),
        )


async def ensure_schedule(client: Client, task_queue: str) -> None:
    """Register the sweep once (later starts find it already there)."""
    try:
        await client.create_schedule(
            SWEEP_SCHEDULE,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    SWEEP_WORKFLOW, id=f"{SWEEP_SCHEDULE}-run", task_queue=task_queue
                ),
                spec=ScheduleSpec(cron_expressions=[SWEEP_CRON]),
            ),
        )
        log.info("digests.schedule_created", schedule=SWEEP_SCHEDULE)
    except ScheduleAlreadyRunningError:
        pass
