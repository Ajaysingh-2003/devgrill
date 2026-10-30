"""Product cache in Redis-compatible Valkey.

Keys are `product:<id>`. The prefix setting namespaces them when the cached shape changes:
with CACHE_KEY_PREFIX=v2: the key becomes `v2:product:<id>`, and every old entry is
invisible until it is written again.
"""

from __future__ import annotations

import json
import logging
import random
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
