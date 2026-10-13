"""Valkey client (wire-compatible with the redis-py client)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    from devgrill.config import Settings


def create_valkey(settings: Settings) -> Redis:
    return Redis.from_url(settings.valkey_url, decode_responses=True)


async def ping(client: Redis) -> None:
    await client.ping()
