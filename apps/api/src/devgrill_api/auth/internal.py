"""HMAC signatures for server-to-server calls from the web app (the sign-in hook).

Signature = hex(HMAC-SHA256(INTERNAL_HMAC_SECRET, f"{timestamp}.{raw body}")), sent as
`X-DevGrill-Signature` with the Unix timestamp in `X-DevGrill-Timestamp`. Requests more than
five minutes old (or from the future) are rejected so a captured request can't be replayed
later. The web side lives in apps/web/lib/internal-api.ts.
"""

from __future__ import annotations

import hashlib
import hmac
import time

TIMESTAMP_HEADER = "x-devgrill-timestamp"
SIGNATURE_HEADER = "x-devgrill-signature"
MAX_SKEW_S = 300


class SignatureError(Exception):
    pass


def sign(secret: str, timestamp: int, body: bytes) -> str:
    message = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(
    secret: str,
    timestamp: str | None,
    signature: str | None,
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
    if not hmac.compare_digest(sign(secret, ts, body), signature):
        raise SignatureError("bad signature")
