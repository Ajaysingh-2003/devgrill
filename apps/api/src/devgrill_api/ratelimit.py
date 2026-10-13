"""Fixed-window rate limits in Valkey, with IETF RateLimit headers (docs/PLAN.md §10.1).

Limits are keyed by client IP. Per-user buckets for expensive actions (starting attempts,
verify, war-room messages) arrive with those endpoints in phase 4. If Valkey is down the
limiter fails open and logs: losing rate limits briefly is better than losing the API.
Behind a proxy, run uvicorn with --proxy-headers so `request.client` is the real client.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from fastapi import Request, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError

from devgrill.config import Settings
from devgrill_api.errors import AppError

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    reset_s: int


async def hit(
    valkey: Redis, key: str, limit: int, window_s: int, *, now: float | None = None
) -> Decision:
    current = int(now if now is not None else time.time())
    window = current // window_s
    bucket_key = f"rl:{key}:{window}"
    count = int(await valkey.incr(bucket_key))
    if count == 1:
        await valkey.expire(bucket_key, window_s + 1)
    reset = window_s - current % window_s
    return Decision(
        allowed=count <= limit, limit=limit, remaining=max(0, limit - count), reset_s=reset
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(
    bucket: str, *, limit: int | None = None, window_s: int | None = None
) -> Callable[[Request, Response], Awaitable[None]]:
    """A dependency enforcing `limit` requests per `window_s` per client for `bucket`."""

    async def dependency(request: Request, response: Response) -> None:
        settings: Settings = request.app.state.settings
        if not settings.rate_limit_enabled:
            return
        max_requests = limit or settings.rate_limit_default
        window = window_s or settings.rate_limit_window_s
        try:
            decision = await hit(
                request.app.state.valkey, f"{bucket}:{client_ip(request)}", max_requests, window
            )
        except RedisError as exc:
            log.warning("rate_limit_unavailable", error=type(exc).__name__, bucket=bucket)
            return
        headers = {
            "RateLimit-Policy": f'"{bucket}";q={decision.limit};w={window}',
            "RateLimit": f'"{bucket}";r={decision.remaining};t={decision.reset_s}',
        }
        if not decision.allowed:
            raise AppError(
                429,
                "rate_limited",
                "Too many requests. Try again shortly.",
                headers={**headers, "Retry-After": str(decision.reset_s)},
            )
        response.headers.update(headers)

    return dependency
