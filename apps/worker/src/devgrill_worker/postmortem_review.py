"""PostmortemReview: grade one submitted postmortem (ADR 016).

Started by the API when a postmortem is submitted (or a failed review is asked for again).
The grading activity retries on transient errors; if it still fails, the player is told the
review couldn't be finished and may ask again. Deterministic: no I/O here.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from devgrill.infra.assist import REVIEW_WORKFLOW
    from devgrill_worker.ai_activities import AiActivities, ReviewFailedInput

#: The judge answers in well under a minute; the SDK retries and the fallback model fit too.
GRADE_TIMEOUT = timedelta(minutes=4)
GRADE_RETRY = RetryPolicy(initial_interval=timedelta(seconds=10), maximum_attempts=3)
STEP_TIMEOUT = timedelta(seconds=30)
STEP_RETRY = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=5)


@workflow.defn(name=REVIEW_WORKFLOW)
class PostmortemReview:
    @workflow.run
    async def run(self, attempt_id: str) -> bool:
        try:
            return await workflow.execute_activity_method(
                AiActivities.grade,
                attempt_id,
                start_to_close_timeout=GRADE_TIMEOUT,
                retry_policy=GRADE_RETRY,
            )
        except ActivityError:
            await workflow.execute_activity_method(
                AiActivities.failed,
                ReviewFailedInput(attempt_id),
                start_to_close_timeout=STEP_TIMEOUT,
                retry_policy=STEP_RETRY,
            )
            return False
