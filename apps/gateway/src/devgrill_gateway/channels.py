"""The workspace's two WebSockets: the terminal and the telemetry stream (PLAN §12.3).

Both are opened with a single-use ticket from the API (`POST /v1/attempts/{id}/ws-ticket`)
and from an allowed Origin (browsers send it; it blocks cross-site WebSocket hijacking).

Terminal: binary frames are keystrokes in and screen bytes out; text frames are JSON control
messages ({"type": "resize", "cols", "rows"} and {"type": "ping"}). The shell runs inside tmux,
so a reload re-attaches to the same session. Output is recorded as an asciicast v2 file in
object storage (the replay, and the AI's context in phase 6).

Telemetry: {"type": "hello"} (metric names and SLO), {"type": "history"} (the last 30 minutes
of samples), then live {"type": "sample"} and batched {"type": "logs"} frames. A slow client
never slows the sandbox: log lines are dropped oldest-first and counted.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from typing import Any

import structlog
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from devgrill.config import Settings
from devgrill.infra.models import Recording
from devgrill.infra.objectstore import ObjectStore, ObjectStoreError
from devgrill.infra.signing import redeem_ticket
from devgrill.sandbox.driver import SandboxError
from devgrill.sandbox.lifecycle import (
    HISTORY_SAMPLES,
    SAMPLE_EVERY_S,
    SIGNAL_TOUCH,
    samples_key,
    telemetry_channel,
    workflow_id,
)
from devgrill_gateway.control import ControlBridges
from devgrill_gateway.operations import OperationError, Operations

log = structlog.get_logger(__name__)

MAX_FRAME_BYTES = 64 * 1024
MAX_RECORDING_BYTES = 5 * 1024 * 1024
TOUCH_EVERY_S = 20.0
LOG_BUFFER = 2000
LOG_BATCH = 300
LOG_FLUSH_S = 0.25
PING_EVERY_S = 20.0
STATE_CHECK_S = 5.0

# Close codes (4000-4999 are ours): the browser decides whether reconnecting makes sense.
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403
CLOSE_NOT_READY = 4409
CLOSE_ENDED = 4410


class Asciicast:
    """asciicast v2: a JSON header line, then [seconds, "o", text] output events."""

    def __init__(self, cols: int, rows: int) -> None:
        self._started = time.monotonic()
        header = {"version": 2, "width": cols, "height": rows, "timestamp": int(time.time())}
        self._lines = [json.dumps(header)]
        self._size = len(self._lines[0])
        self.truncated = False

    def _event(self, kind: str, data: str) -> None:
        if self.truncated:
            return
        line = json.dumps([round(time.monotonic() - self._started, 4), kind, data])
        if self._size + len(line) > MAX_RECORDING_BYTES:
            self.truncated = True
            return
        self._lines.append(line)
        self._size += len(line) + 1

    def output(self, data: bytes) -> None:
        self._event("o", data.decode("utf-8", errors="replace"))

    def resize(self, cols: int, rows: int) -> None:
        self._event("r", f"{cols}x{rows}")

    def payload(self) -> bytes:
        return ("\n".join(self._lines) + "\n").encode("utf-8")

    @property
    def has_output(self) -> bool:
        return len(self._lines) > 1


class Channels:
    def __init__(
        self,
        *,
        settings: Settings,
        ops: Operations,
        bridges: ControlBridges,
        valkey: Any,
        store: ObjectStore,
    ) -> None:
        self.settings = settings
        self.ops = ops
        self.bridges = bridges
        self.valkey = valkey
        self.store = store
        self._temporal: Any = None
        self._last_touch: dict[uuid.UUID, float] = {}

    # ------------------------------------------------------------------------- admission

    @staticmethod
    async def _refuse(ws: WebSocket, code: int, reason: str = "") -> None:
        """Accept, then close with our code: a refusal before accepting reaches the browser as a
        bare HTTP 403 (close code 1006), and the client couldn't tell "wait" from "give up"."""
        await ws.accept()
        await ws.close(code=code, reason=reason[:120])

    async def _admit(self, ws: WebSocket, attempt_id: uuid.UUID, ticket: str, kind: str) -> bool:
        """Origin and ticket checks; refuses the socket (with a close code) when they fail."""
        origin = ws.headers.get("origin")
        if origin is not None and origin not in self.settings.ws_origins:
            await self._refuse(ws, CLOSE_FORBIDDEN_ORIGIN, "origin not allowed")
            return False
        redeemed = await redeem_ticket(self.valkey, ticket)
        if redeemed is None or redeemed.attempt_id != str(attempt_id) or redeemed.kind != kind:
            log.warning("gateway.ticket_refused", attempt_id=str(attempt_id), kind=kind)
            await self._refuse(ws, CLOSE_UNAUTHORIZED, "bad or used ticket")
            return False
        return True

    async def _touch(self, attempt_id: uuid.UUID) -> None:
        """Tell the workflow the player is active (resets the idle timer), at most every 20 s."""
        now = time.monotonic()
        if now - self._last_touch.get(attempt_id, 0) < TOUCH_EVERY_S:
            return
        self._last_touch[attempt_id] = now
        try:
            if self._temporal is None:
                from devgrill.infra.workflows import connect_temporal

                self._temporal = await connect_temporal(self.settings)
            await self._temporal.get_workflow_handle(workflow_id(str(attempt_id))).signal(
                SIGNAL_TOUCH
            )
        except Exception as exc:
            log.warning("gateway.touch_failed", attempt_id=str(attempt_id), error=str(exc))

    # -------------------------------------------------------------------------- terminal

    async def terminal(
        self, ws: WebSocket, attempt_id: uuid.UUID, ticket: str, cols: int, rows: int
    ) -> None:
        if not await self._admit(ws, attempt_id, ticket, "terminal"):
            return
        try:
            sb = await self.ops.sandbox(attempt_id)
        except OperationError as exc:
            code = CLOSE_ENDED if exc.code == "attempt_ended" else CLOSE_NOT_READY
            await self._refuse(ws, code, exc.detail)
            return
        await ws.accept()
        self.bridges.ensure(attempt_id)
        cols, rows = max(20, min(cols, 400)), max(5, min(rows, 200))
        try:
            pty = await self.ops.driver.exec_pty(
                sb.handle,
                sb.bundle.base_app.shell_service,
                ["tmux", "new-session", "-A", "-s", "oncall"],
                cols=cols,
                rows=rows,
                env={"TERM": "xterm-256color", "LANG": "C.UTF-8"},
            )
        except SandboxError as exc:
            await ws.close(code=CLOSE_NOT_READY, reason=str(exc)[:120])
            return
        cast = Asciicast(cols, rows)
        log.info("terminal.opened", attempt_id=str(attempt_id))

        async def screen_to_browser() -> None:
            while (data := await pty.read()) is not None:
                cast.output(data)
                await ws.send_bytes(data)

        async def browser_to_shell() -> None:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if (data := message.get("bytes")) is not None:
                    if len(data) > MAX_FRAME_BYTES:
                        await ws.close(code=1009)
                        return
                    await pty.write(data)
                    await self._touch(attempt_id)
                elif (text := message.get("text")) is not None:
                    if len(text) > MAX_FRAME_BYTES:
                        await ws.close(code=1009)
                        return
                    await self._control(ws, pty, cast, text)

        async def finish() -> None:
            with contextlib.suppress(Exception):
                await pty.close()
            if ws.client_state is WebSocketState.CONNECTED:
                with contextlib.suppress(Exception):
                    await ws.close()
            await self._save_recording(attempt_id, cast)
            log.info("terminal.closed", attempt_id=str(attempt_id))

        try:
            await _first_to_finish(screen_to_browser(), browser_to_shell())
        finally:
            # Shielded: a disconnect can cancel this handler; the shell must still be released
            # and the recording must still land.
            await asyncio.shield(finish())

    @staticmethod
    async def _control(ws: WebSocket, pty: Any, cast: Asciicast, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return
        match message.get("type"):
            case "resize":
                cols = max(20, min(int(message.get("cols", 80)), 400))
                rows = max(5, min(int(message.get("rows", 24)), 200))
                await pty.resize(cols, rows)
                cast.resize(cols, rows)
            case "ping":
                await ws.send_text(json.dumps({"type": "pong", "t": message.get("t")}))

    async def _save_recording(self, attempt_id: uuid.UUID, cast: Asciicast) -> None:
        if not cast.has_output:
            return
        data = cast.payload()
        key = f"recordings/{attempt_id}/terminal-{uuid.uuid4().hex}.cast"
        try:
            await self.store.put(key, data)
        except (ObjectStoreError, OSError) as exc:
            log.warning("terminal.recording_not_saved", attempt_id=str(attempt_id), error=str(exc))
            return
        async with self.ops.session_factory() as session, session.begin():
            session.add(
                Recording(attempt_id=attempt_id, kind="terminal", object_key=key, bytes=len(data))
            )

    # ------------------------------------------------------------------------- telemetry

    async def telemetry(self, ws: WebSocket, attempt_id: uuid.UUID, ticket: str) -> None:
        if not await self._admit(ws, attempt_id, ticket, "telemetry"):
            return
        try:
            sb = await self.ops.sandbox(attempt_id, playable=False)
        except OperationError as exc:
            code = CLOSE_ENDED if exc.code == "attempt_ended" else CLOSE_NOT_READY
            await self._refuse(ws, code, exc.detail)
            return
        await ws.accept()
        app = sb.bundle.base_app
        slo = sb.bundle.scenario.slo
        await ws.send_json(
            {
                "type": "hello",
                "metrics": list(app.metrics),
                "every_s": SAMPLE_EVERY_S,
                "slo": {
                    k: v.model_dump(exclude_none=True)
                    for k, v in (slo.targets() if slo else {}).items()
                },
            }
        )
        history = await self.valkey.lrange(samples_key(str(attempt_id)), 0, HISTORY_SAMPLES - 1)
        await ws.send_json(
            {"type": "history", "samples": [json.loads(s) for s in reversed(history)]}
        )

        services = [n for n, s in app.services.items() if s.logs]
        pending: deque[dict[str, Any]] = deque(maxlen=LOG_BUFFER)
        dropped = 0

        async def collect_logs() -> None:
            nonlocal dropped
            async for line in self.ops.driver.follow_logs(sb.handle, services=services):
                if len(pending) == pending.maxlen:
                    dropped += 1  # the oldest line falls off: a slow tab never blocks
                pending.append(
                    {"ts": line.ts.isoformat(), "service": line.service, "line": line.line[:4000]}
                )

        async def send_logs() -> None:
            nonlocal dropped
            while True:
                await asyncio.sleep(LOG_FLUSH_S)
                if not pending and not dropped:
                    continue
                batch = [pending.popleft() for _ in range(min(LOG_BATCH, len(pending)))]
                await ws.send_json({"type": "logs", "lines": batch, "dropped": dropped})
                dropped = 0

        async def forward_samples() -> None:
            pubsub = self.valkey.pubsub()
            await pubsub.subscribe(telemetry_channel(str(attempt_id)))
            last_sent = time.monotonic()
            try:
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=PING_EVERY_S
                    )
                    if message is None:
                        # None also comes straight back for the subscribe confirmation: ping
                        # only after a real quiet spell, to keep proxies from closing the socket.
                        if time.monotonic() - last_sent >= PING_EVERY_S:
                            await ws.send_json({"type": "ping", "t": time.time()})
                            last_sent = time.monotonic()
                        continue
                    sample = {"type": "sample", **json.loads(message["data"])}
                    await ws.send_text(json.dumps(sample))
                    last_sent = time.monotonic()
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()

        async def watch_end() -> None:
            while True:
                await asyncio.sleep(STATE_CHECK_S)
                try:
                    await self.ops.sandbox(attempt_id, playable=False)
                except OperationError:
                    await ws.send_json({"type": "ended"})
                    await ws.close(code=CLOSE_ENDED)
                    return

        async def until_disconnect() -> None:
            while (await ws.receive())["type"] != "websocket.disconnect":
                pass

        await _first_to_finish(
            collect_logs(), send_logs(), forward_samples(), watch_end(), until_disconnect()
        )
        if ws.client_state is WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await ws.close()


async def _first_to_finish(*coros: Any) -> None:
    """Run coroutines together; when one finishes (or fails), cancel the rest."""
    tasks = [asyncio.create_task(c) for c in coros]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect | ConnectionError):
                log.warning("gateway.channel_error", error=repr(exc))
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
