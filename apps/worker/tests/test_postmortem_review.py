"""PostmortemReview (ADR 016): grade once; when grading keeps failing, tell the player."""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from devgrill_worker.ai_activities import ReviewFailedInput
from devgrill_worker.postmortem_review import PostmortemReview


@pytest.fixture
async def env():
    try:
        environment = await WorkflowEnvironment.start_time_skipping()
    except Exception as exc:
        pytest.skip(f"time-skipping test server unavailable: {exc}")
    async with environment:
        yield environment


async def review(env: WorkflowEnvironment, *, crashes: bool) -> tuple[bool, list[str], int]:
    calls: list[str] = []
    failed: list[str] = []

    @activity.defn(name="postmortem.grade")
    async def grade(attempt_id: str) -> bool:
        calls.append(attempt_id)
        if crashes:
            raise ApplicationError("the database went away")
        return True

    @activity.defn(name="postmortem.review_failed")
    async def review_failed(inp: ReviewFailedInput) -> None:
        failed.append(inp.attempt_id)

    queue = f"q-{uuid.uuid4().hex[:8]}"
    async with Worker(
        env.client,
        task_queue=queue,
        workflows=[PostmortemReview],
        activities=[grade, review_failed],
    ):
        result = await env.client.execute_workflow(
            PostmortemReview.run, "a1", id=f"review-{uuid.uuid4().hex[:8]}", task_queue=queue
        )
    return result, failed, len(calls)


async def test_a_review_grades_once(env) -> None:  # type: ignore[no-untyped-def]
    assert await review(env, crashes=False) == (True, [], 1)


async def test_a_review_that_keeps_failing_is_reported(env) -> None:  # type: ignore[no-untyped-def]
    # Three tries (the retry policy), then the player is told.
    assert await review(env, crashes=True) == (False, ["a1"], 3)
