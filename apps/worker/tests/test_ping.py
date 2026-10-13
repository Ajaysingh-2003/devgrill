import uuid

import pytest
from temporalio.testing import ActivityEnvironment
from temporalio.worker import Worker

from devgrill.config import Settings
from devgrill.infra.workflows import connect_temporal
from devgrill_worker.activities import pong
from devgrill_worker.workflows import ACTIVITIES, WORKFLOWS, PingWorkflow


async def test_pong_activity() -> None:
    assert await ActivityEnvironment().run(pong, "x") == "pong:x"


@pytest.mark.integration
async def test_ping_workflow_end_to_end() -> None:
    """Needs `just deps-up` (Temporal dev server). Runs an in-process worker on a unique queue."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    client = await connect_temporal(settings)
    queue = f"test-{uuid.uuid4().hex[:8]}"
    async with Worker(client, task_queue=queue, workflows=WORKFLOWS, activities=ACTIVITIES):
        result = await client.execute_workflow(
            PingWorkflow.run, "it", id=f"ping-{uuid.uuid4().hex[:8]}", task_queue=queue
        )
    assert result == "pong:it"
