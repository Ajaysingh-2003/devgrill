"""Signed service-to-service requests (API -> gateway) and single-use WebSocket tickets.

Requests: hex(HMAC-SHA256(INTERNAL_HMAC_SECRET, "{ts}\\n{METHOD}\\n{path?query}\\n{body}")),
sent as X-DevGrill-Signature with X-DevGrill-Timestamp. Method and path are signed too, so a
captured GET can't be replayed against another endpoint. Five minutes of clock skew allowed.

Tickets: 32 random bytes, stored in Valkey for a minute and deleted by the first read (GETDEL),
bound to one attempt, one owner and one channel (terminal or telemetry). Browsers can't send
headers on a WebSocket, so the ticket travels in the URL; being single-use and short-lived,
a leaked one is worthless (PLAN §10.1).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Literal

from redis.asyncio import Redis

TIMESTAMP_HEADER = "x-devgrill-timestamp"
SIGNATURE_HEADER = "x-devgrill-signature"
MAX_SKEW_S = 300

TicketKind = Literal["terminal", "telemetry"]


class SignatureError(Exception):
    pass


def sign_request(secret: str, timestamp: int, method: str, target: str, body: bytes) -> str:
    message = f"{timestamp}\n{method.upper()}\n{target}\n".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signed_headers(secret: str, method: str, target: str, body: bytes) -> dict[str, str]:
    ts = int(time.time())
    return {
        TIMESTAMP_HEADER: str(ts),
        SIGNATURE_HEADER: sign_request(secret, ts, method, target, body),
    }


def verify_request(
    secret: str,
    timestamp: str | None,
    signature: str | None,
    method: str,
    target: str,
    body: bytes,
    *,
    now: float | None = None,
) -> None:
    if not secret:
        raise SignatureError("internal calls are not configured")
    if not timestamp or not signature:
        raise SignatureError("missing signature")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise SignatureError("bad timestamp") from exc
    if abs((now if now is not None else time.time()) - ts) > MAX_SKEW_S:
        raise SignatureError("stale request")
    if not hmac.compare_digest(sign_request(secret, ts, method, target, body), signature):
        raise SignatureError("bad signature")


@dataclass(frozen=True, slots=True)
class Ticket:
    attempt_id: str
    kind: TicketKind
    #: "user:<uuid>" or "guest:<hash>", for logs and per-owner limits.
    owner: str


def _key(token: str) -> str:
    return f"wsticket:{token}"


async def issue_ticket(valkey: Redis, ticket: Ticket, ttl_s: int) -> str:
    token = secrets.token_urlsafe(32)
    await valkey.set(_key(token), json.dumps(asdict(ticket)), ex=ttl_s)
    return token


async def redeem_ticket(valkey: Redis, token: str) -> Ticket | None:
    """The ticket, or None if it never existed, expired or was already used."""
    if not token or len(token) > 100:
        return None
    raw = await valkey.getdel(_key(token))
    if raw is None:
        return None
    data = json.loads(raw)
    return Ticket(attempt_id=data["attempt_id"], kind=data["kind"], owner=data["owner"])
