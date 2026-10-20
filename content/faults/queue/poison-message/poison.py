"""Push a malformed order to the head of the queue (runs inside the tools container)."""

import json
import os
import time

import redis

client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
# quantity 0 makes charge() raise every time; with MAX_ATTEMPTS=0 it never leaves the queue.
poison = {"id": 1, "user_id": 1, "product_id": 1042, "quantity": 0, "enqueued_at": time.time()}
client.rpush("orders:pending", json.dumps(poison))
print("poisoned orders:pending")
