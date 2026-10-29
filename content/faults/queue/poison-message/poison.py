"""Push a malformed order to the head of the queue (runs inside the tools container).

A partner integration's test message: no real order behind it (id 0) and quantity 0, so
charge() rejects it every time. With retries set to forever it never leaves the head.
"""

import json
import os
import time

import redis

client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
poison = {
    "id": 0,
    "user_id": 0,
    "product_id": 1042,
    "quantity": 0,
    "enqueued_at": time.time(),
    "source": "partner-sync",
}
client.rpush("orders:pending", json.dumps(poison))
print("poisoned orders:pending")
