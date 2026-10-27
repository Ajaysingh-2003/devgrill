"""Daily and weekly challenges roll over at midnight IST (Temporal schedule).

The API also creates a window's challenge on first request, so a missed run costs nothing;
the schedule makes the pick ready before anyone asks (and is where the daily's pre-warmed
sandboxes will start, later).
"""

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

# Activity-side code: kept out of the workflow sandbox (it seeds random at import time).
with workflow.unsafe.imports_passed_through():
    import structlog
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from devgrill.domain.streaks import DEFAULT_TIMEZONE
    from devgrill.infra.repositories import challenges

log = structlog.get_logger(__name__)

ROLLOVER_WORKFLOW = "ChallengeRollover"
ROLLOVER_SCHEDULE = "challenge-rollover"
#: A minute past midnight IST: the new window has begun everywhere the API runs.
ROLLOVER_CRON = "1 0 * * *"


class ChallengeActivities:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    @activity.defn(name="challenges.ensure")
    async def ensure(self) -> list[str]:
        async with self.session_factory() as session, session.begin():
            made = await challenges.ensure(session, datetime.now(UTC))
        log.info("challenges.rolled_over", kinds=made)
        return made


@workflow.defn(name=ROLLOVER_WORKFLOW)
class ChallengeRollover:
    @workflow.run
    async def run(self) -> list[str]:
        return await workflow.execute_activity_method(
            ChallengeActivities.ensure,
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(initial_interval=timedelta(seconds=5), maximum_attempts=10),
        )


async def ensure_schedule(client: Client, task_queue: str) -> None:
    """Register the rollover schedule once (later starts find it already there)."""
    try:
        await client.create_schedule(
            ROLLOVER_SCHEDULE,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    ROLLOVER_WORKFLOW, id=f"{ROLLOVER_SCHEDULE}-run", task_queue=task_queue
                ),
                spec=ScheduleSpec(
                    cron_expressions=[ROLLOVER_CRON], time_zone_name=DEFAULT_TIMEZONE
                ),
            ),
        )
        log.info("challenges.schedule_created", schedule=ROLLOVER_SCHEDULE)
    except ScheduleAlreadyRunningError:
        pass
