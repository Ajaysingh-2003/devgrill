"""Invariant: one order that can never be charged doesn't stop the ones behind it.

Runs in the verifier's probe container with TARGET (the API), PG_DSN (read-only) and
CACHE_HOST (Valkey). Puts a malformed order at the head of orders:pending, places good orders
through the API, and watches them in Postgres. Prints {"good_paid_within_s": seconds or null,
"poison_dead_lettered": 1 or 0}. Removes its message from the queue before it exits.
"""

import json
import os
import random
import time
import uuid

import httpx
import psycopg
import redis

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
QUEUE, DEAD = "orders:pending", "orders:dead"
ORDERS = 5
DEADLINE_S = 30

queue = redis.Redis(host=os.environ["CACHE_HOST"], port=6379, socket_timeout=5)
marker = f"verify-{uuid.uuid4().hex[:12]}"
poison = {
    "id": 0,
    "user_id": 0,
    "product_id": 1042,
    "quantity": 0,
    "enqueued_at": time.time(),
    "source": marker,
}
# The worker takes from the right: this is the front of the line.
queue.rpush(QUEUE, json.dumps(poison))

with httpx.Client(base_url=TARGET, timeout=5) as client:
    ids = []
    for _ in range(ORDERS):
        res = client.post(
            "/orders",
            json={
                "user_id": random.randint(1, 2000),
                "product_id": random.randint(1, 18402),
                "quantity": 1,
            },
        )
        res.raise_for_status()
        ids.append(res.json()["id"])
placed = time.monotonic()

paid_within = None
with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    while time.monotonic() - placed < DEADLINE_S:
        row = conn.execute(
            "SELECT count(*) FROM public.orders WHERE id = ANY(%s) AND status = 'paid'", (ids,)
        ).fetchone()
        if row and row[0] == len(ids):
            paid_within = round(time.monotonic() - placed, 3)
            break
        time.sleep(0.25)


def ours(raw: bytes) -> bool:
    try:
        return json.loads(raw).get("source") == marker
    except ValueError:
        return False


dead = any(ours(raw) for raw in queue.lrange(DEAD, 0, -1))

# Clean up: a worker that retries forever keeps re-queueing it, so look for a few seconds.
end = time.monotonic() + 5
while time.monotonic() < end:
    for raw in queue.lrange(QUEUE, 0, -1):
        if ours(raw):
            queue.lrem(QUEUE, 0, raw)
    time.sleep(0.1)

print(json.dumps({"good_paid_within_s": paid_within, "poison_dead_lettered": int(dead)}))
