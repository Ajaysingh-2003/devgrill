"""Idempotency-Key support for POST/PUT/PATCH (docs/PLAN.md §10.1).

The first request with a key runs and its response (if not a 5xx) is stored in Valkey for
24 hours. A retry with the same key and the same body gets that stored response back, marked
`Idempotent-Replayed: true`. The same key with a different body is a client bug (422); a
retry that arrives while the first is still running gets 409.

Keys are scoped to the caller's credentials (a hash of the Authorization and X-Guest-Token
headers), so one caller can never be served another caller's stored response.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from devgrill_api.errors import problem_response

log = structlog.get_logger(__name__)

HEADER = b"idempotency-key"
_METHODS = {"POST", "PUT", "PATCH"}
_VALID_KEY = re.compile(r"^[\x21-\x7e]{1,255}$")
TTL_S = 24 * 3600
LOCK_TTL_S = 60


@dataclass
class _Captured:
    status: int = 500
    headers: list[list[str]] = field(default_factory=list)
    body: bytearray = field(default_factory=bytearray)


class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _METHODS:
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        raw_key = headers.get(HEADER)
        if raw_key is None:
            await self.app(scope, receive, send)
            return

        key = raw_key.decode("latin-1")
        if not _VALID_KEY.match(key):
            await _send_problem(scope, receive, send, 400, "invalid_idempotency_key")
            return

        body = await _read_body(receive)
        caller = hashlib.sha256(
            headers.get(b"authorization", b"") + b"|" + headers.get(b"x-guest-token", b"")
        ).hexdigest()
        request_hash = hashlib.sha256(
            scope["method"].encode() + b" " + scope["path"].encode() + b"\n" + body
        ).hexdigest()
        store_key = f"idem:{caller}:{hashlib.sha256(raw_key).hexdigest()}"
        valkey: Redis = scope["app"].state.valkey

        try:
            locked = await valkey.set(
                store_key,
                json.dumps({"state": "running", "hash": request_hash}),
                nx=True,
                ex=LOCK_TTL_S,
            )
            if not locked:
                stored = await valkey.get(store_key)
                if stored is not None:
                    record = json.loads(stored)
                    if record["hash"] != request_hash:
                        await _send_problem(scope, receive, send, 422, "idempotency_key_reused")
                        return
                    if record["state"] == "running":
                        await _send_problem(scope, receive, send, 409, "request_in_progress")
                        return
                    await _replay(record, send)
                    return
        except RedisError as exc:
            log.warning("idempotency_unavailable", error=type(exc).__name__)
            await self.app(scope, _replay_body(body), send)
            return

        captured = _Captured()

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                captured.status = message["status"]
                captured.headers = [
                    [k.decode("latin-1"), v.decode("latin-1")]
                    for k, v in message.get("headers", [])
                ]
            elif message["type"] == "http.response.body":
                captured.body.extend(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, _replay_body(body), capture)
        finally:
            try:
                if captured.status >= 500:
                    await valkey.delete(store_key)  # let the client retry
                else:
                    record = {
                        "state": "done",
                        "hash": request_hash,
                        "status": captured.status,
                        "headers": captured.headers,
                        "body": base64.b64encode(bytes(captured.body)).decode(),
                    }
                    await valkey.set(store_key, json.dumps(record), ex=TTL_S)
            except RedisError as exc:
                log.warning("idempotency_store_failed", error=type(exc).__name__)


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay_body(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


async def _replay(record: dict[str, Any], send: Send) -> None:
    headers = [
        (k.encode("latin-1"), v.encode("latin-1"))
        for k, v in record["headers"]
        if k.lower() not in {"content-length", "x-request-id"}
    ]
    body = base64.b64decode(record["body"])
    headers.append((b"content-length", str(len(body)).encode()))
    headers.append((b"idempotent-replayed", b"true"))
    await send({"type": "http.response.start", "status": record["status"], "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_problem(scope: Scope, receive: Receive, send: Send, status: int, code: str) -> None:
    details = {
        "invalid_idempotency_key": "Idempotency-Key must be 1-255 visible ASCII characters.",
        "idempotency_key_reused": "This Idempotency-Key was already used with a different request.",
        "request_in_progress": "A request with this Idempotency-Key is still being processed.",
    }
    response = problem_response(status, code=code, detail=details[code], instance=scope["path"])
    await response(scope, receive, send)
