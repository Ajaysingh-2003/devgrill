"""The orders queue in Valkey: the API enqueues every new order, the worker charges it.

A Valkey list: the API pushes on the left, the worker takes from the right, so orders are
charged in the order they were placed.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

from app import cache
from app.logging_setup import fields

log = logging.getLogger("orders")

QUEUE = "orders:pending"


def enqueue(order: dict[str, Any], product_id: int, quantity: int) -> None:
    """Queue a new order for charging. If Valkey is down the order stays 'pending' in Postgres."""
    message = {
        "id": order["id"],
        "user_id": order["user_id"],
        "product_id": product_id,
        "quantity": quantity,
        "enqueued_at": time.time(),
    }
    try:
        cache.client.lpush(QUEUE, json.dumps(message))
    except redis.RedisError as exc:
        log.warning(
            "order not queued", extra=fields(order_id=order["id"], error=type(exc).__name__)
        )
