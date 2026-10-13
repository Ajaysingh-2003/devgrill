"""`devgrill-worker` runs the worker; `devgrill-worker ping` executes PingWorkflow once."""

from __future__ import annotations

import argparse
import asyncio
import uuid

import structlog
from temporalio.worker import Worker

from devgrill.config import get_settings
from devgrill.infra.workflows import connect_temporal
from devgrill.observability import configure_logging
from devgrill_worker.workflows import ACTIVITIES, WORKFLOWS, PingWorkflow

log = structlog.get_logger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    client = await connect_temporal(settings)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=WORKFLOWS,
        activities=ACTIVITIES,
    )
    log.info("worker_started", task_queue=settings.temporal_task_queue)
    await worker.run()


async def run_ping(name: str) -> str:
    settings = get_settings()
    client = await connect_temporal(settings)
    return await client.execute_workflow(
        PingWorkflow.run,
        name,
        id=f"ping-{uuid.uuid4().hex[:12]}",
        task_queue=settings.temporal_task_queue,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="devgrill-worker")
    sub = parser.add_subparsers(dest="command")
    ping = sub.add_parser("ping", help="run PingWorkflow once against a running worker")
    ping.add_argument("--name", default="devgrill")
    args = parser.parse_args()

    configure_logging(get_settings())
    if args.command == "ping":
        result = asyncio.run(run_ping(args.name))
        print(result)
    else:
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
