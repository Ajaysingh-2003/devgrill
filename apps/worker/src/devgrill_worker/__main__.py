"""`devgrill-worker` runs the worker; `devgrill-worker ping` executes PingWorkflow once."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from pathlib import Path

import structlog
from temporalio.worker import Worker

from devgrill.config import get_settings
from devgrill.infra import db
from devgrill.infra.cache import create_valkey
from devgrill.infra.objectstore import ObjectStore
from devgrill.infra.workflows import connect_temporal
from devgrill.observability import configure_logging
from devgrill.sandbox.compose import ComposeDriver
from devgrill_worker.sandbox_activities import SandboxActivities
from devgrill_worker.workflows import ACTIVITIES, WORKFLOWS, PingWorkflow

log = structlog.get_logger(__name__)

PROBE_BUILD_DIR = Path("infra/sandbox/probe")
#: Built from source when running from a checkout; pulled (prebuilt) otherwise.
HAVE_PROBE_SOURCE = PROBE_BUILD_DIR.is_dir()


async def run_worker() -> None:
    settings = get_settings()
    client = await connect_temporal(settings)
    engine = db.create_engine(settings)
    valkey = create_valkey(settings)
    driver = ComposeDriver(
        probe_image=settings.sandbox_probe_image,
        probe_build_dir=PROBE_BUILD_DIR if HAVE_PROBE_SOURCE else None,
        healthy_timeout_s=settings.sandbox_provision_timeout_s,
    )
    sandbox = SandboxActivities(
        settings=settings,
        driver=driver,
        session_factory=db.create_session_factory(engine),
        valkey=valkey,
        store=ObjectStore.from_settings(settings),
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=WORKFLOWS,
        activities=[*ACTIVITIES, *sandbox.all()],
    )
    log.info("worker_started", task_queue=settings.temporal_task_queue)
    try:
        await worker.run()
    finally:
        await driver.close()
        await valkey.aclose()
        await engine.dispose()


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
