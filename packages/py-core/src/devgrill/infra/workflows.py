"""Temporal client helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from temporalio.client import Client

if TYPE_CHECKING:
    from devgrill.config import Settings


async def connect_temporal(settings: Settings) -> Client:
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


async def ping(client: Client) -> None:
    # A cheap round trip that proves the frontend service and namespace are reachable.
    await client.service_client.check_health()
