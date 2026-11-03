"""Product cache in Redis-compatible Valkey.

Keys are `product:<id>`. The prefix setting namespaces them when the cached shape changes:
with CACHE_KEY_PREFIX=v2: the key becomes `v2:product:<id>`, and every old entry is
invisible until it is written again.
"""

from __future__ import annotations

import json
import logging
import random
import secrets
from typing import Any

import redis

from app import settings
from app.logging_setup import fields

log = logging.getLogger("cache")

client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=1.0, socket_connect_timeout=1.0)


def key(product_id: int) -> str:
    return f"{settings.CACHE_KEY_PREFIX}product:{product_id}"


def get(product_id: int) -> dict[str, Any] | None:
    try:
        raw = client.get(key(product_id))
    except redis.RedisError as exc:
        log.warning("cache unavailable", extra=fields(error=type(exc).__name__))
        return None
    if raw is None:
        return None
    return json.loads(raw)


def _ttl() -> int:
    """The TTL give or take 10%: entries cached together don't all expire together."""
    return max(1, round(settings.CACHE_TTL_SECONDS * random.uniform(0.9, 1.1)))


def set(product_id: int, product: dict[str, Any]) -> None:
    if settings.CACHE_TTL_SECONDS <= 0:
        return
    try:
        client.set(key(product_id), json.dumps(product, default=str), ex=_ttl())
    except redis.RedisError as exc:
        log.warning("cache write failed", extra=fields(error=type(exc).__name__))


def invalidate(product_id: int) -> None:
    try:
        client.delete(key(product_id))
    except redis.RedisError as exc:
        log.warning("cache invalidate failed", extra=fields(error=type(exc).__name__))


def healthy() -> bool:
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False


DEALS_KEY = "deals"
DEALS_REFRESH_LOCK = "deals:refresh"


def get_deals() -> dict[str, Any] | None:
    try:
        raw = client.get(DEALS_KEY)
    except redis.RedisError as exc:
        log.warning("cache unavailable", extra=fields(error=type(exc).__name__))
        return None
    return None if raw is None else json.loads(raw)


def set_deals(page: dict[str, Any]) -> None:
    try:
        client.set(DEALS_KEY, json.dumps(page, default=str), ex=settings.DEALS_TTL_S)
    except redis.RedisError as exc:
        log.warning("cache write failed", extra=fields(error=type(exc).__name__))


def claim_deals_refresh() -> bool:
    """True for the one request that gets to rebuild the deals page (for 30 s at most)."""
    try:
        return bool(client.set(DEALS_REFRESH_LOCK, "1", nx=True, ex=30))
    except redis.RedisError:
        return False


def _likes_key(product_id: int) -> str:
    return f"likes:{product_id}"


def like(product_id: int, user_id: int) -> None:
    """A shopper likes a product (the heart on its page). Liking twice changes nothing."""
    client.sadd(_likes_key(product_id), user_id)


def liked(product_id: int, user_id: int) -> tuple[bool, int]:
    """Whether this shopper likes the product, and how many shoppers do."""
    pipe = client.pipeline(transaction=False)
    pipe.sismember(_likes_key(product_id), user_id)
    pipe.scard(_likes_key(product_id))
    mine, count = pipe.execute()
    return bool(mine), int(count)


def create_session(user_id: int) -> str | None:
    """A sign-in: a random token for `user_id`, kept for SESSION_TTL_S. None if Valkey refused."""
    token = secrets.token_urlsafe(24)
    try:
        client.set(f"session:{token}", user_id, ex=settings.SESSION_TTL_S)
    except redis.RedisError as exc:
        log.error("session not saved", extra=fields(error=type(exc).__name__, detail=str(exc)))
        return None
    return token


def session_user(token: str) -> int | None:
    """The signed-in user, or None when the session is gone (expired, evicted or made up)."""
    try:
        raw = client.get(f"session:{token}")
    except redis.RedisError as exc:
        log.warning("cache unavailable", extra=fields(error=type(exc).__name__))
        return None
    return None if raw is None else int(raw)
