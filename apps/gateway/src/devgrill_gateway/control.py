"""The control bridge: answers the in-sandbox `devgrill` CLI (ADR 014).

The probe runs `dg-relay` on `control:7000` inside the sandbox network. The gateway holds that
process's stdin and stdout through a Docker exec: each CLI request arrives as a JSON line, is
performed with the same `Operations` as the workspace (source "cli"), and the answer goes back
as a JSON line. One bridge per attempt, started when a terminal connects.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

import structlog

from devgrill.sandbox.driver import SandboxError
from devgrill_gateway.operations import OperationError, Operations

log = structlog.get_logger(__name__)

# Stop a stale relay first. The pattern is anchored to the relay process's exact command line:
# this shell's own command line contains the same path, and an unanchored pattern kills it.
RELAY = [
    "sh",
    "-c",
    "pkill -f '^python3 /usr/local/bin/dg-relay$'; exec python3 /usr/local/bin/dg-relay",
]


async def dispatch(
    ops: Operations, attempt_id: uuid.UUID, request: dict[str, Any]
) -> tuple[int, Any]:
    """One CLI request -> (status, body)."""
    method = str(request.get("method", "GET")).upper()
    url = urlsplit(str(request.get("path", "/")))
    parts = [p for p in url.path.split("/") if p]
    query = parse_qs(url.query)
    body = request.get("body") or {}
    if not isinstance(body, dict):
        body = {}
    try:
        match method, parts:
            case "GET", ["status"]:
                return 200, await ops.status(attempt_id)
            case "GET", ["logs", service]:
                tail = int((query.get("tail") or ["100"])[0])
                return 200, await ops.logs(attempt_id, service, tail)
            case "POST", ["restart", service]:
                return 200, await ops.restart(attempt_id, service, "cli")
            case "POST", ["deploy"]:
                return 200, await ops.deploy(attempt_id, body.get("service"), "cli")
            case "POST", ["rollback"]:
                return 200, await ops.rollback(
                    attempt_id, body.get("service"), str(body.get("sha", "")), "cli"
                )
            case "GET", ["history"]:
                return 200, await ops.deploys(attempt_id, (query.get("service") or [None])[0])
            case (("GET" | "POST"), ["flags"]):
                return 200, await ops.flags(attempt_id)
            case _:
                return 404, {"error": f"unknown command {method} {url.path}"}
    except OperationError as exc:
        return exc.status, {"error": exc.detail}
    except (SandboxError, ValueError) as exc:
        return 502, {"error": str(exc)[:500]}


class ControlBridges:
    def __init__(self, ops: Operations) -> None:
        self.ops = ops
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    def ensure(self, attempt_id: uuid.UUID) -> None:
        task = self._tasks.get(attempt_id)
        if task is None or task.done():
            self._tasks[attempt_id] = asyncio.create_task(self._run(attempt_id))

    async def _run(self, attempt_id: uuid.UUID) -> None:
        try:
            sb = await self.ops.sandbox(attempt_id, playable=False)
            relay = await self.ops.driver.attach_probe(sb.handle, RELAY)
        except (OperationError, SandboxError) as exc:
            log.warning("control.unavailable", attempt_id=str(attempt_id), error=str(exc))
            return
        log.info("control.bridge_started", attempt_id=str(attempt_id))
        write_lock = asyncio.Lock()
        inflight: set[asyncio.Task[None]] = set()

        async def answer(request: dict[str, Any]) -> None:
            # Requests run concurrently: a slow deploy must not block `devgrill status`.
            status, body = await dispatch(self.ops, attempt_id, request)
            reply = json.dumps({"id": request.get("id"), "status": status, "body": body})
            async with write_lock:
                await relay.write(reply.encode() + b"\n")

        buffer = b""
        try:
            while (chunk := await relay.read()) is not None:
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        request = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    task = asyncio.create_task(answer(request))
                    inflight.add(task)
                    task.add_done_callback(inflight.discard)
        except (ConnectionError, OSError, SandboxError) as exc:
            log.info("control.bridge_closed", attempt_id=str(attempt_id), error=str(exc))
        finally:
            for task in inflight:
                task.cancel()
            with contextlib.suppress(Exception):
                await relay.close()

    async def close(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
