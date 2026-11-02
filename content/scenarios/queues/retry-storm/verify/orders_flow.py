"""Invariant: new orders get charged within seconds, and no order is left pending.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN (read-only). Places
orders through the API, then watches their status in Postgres. Prints
{"paid_within_s": seconds or null, "stale_pending": orders pending for over a minute}.
"""

import json
import os
import random
import time

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
ORDERS = 20
DEADLINE_S = 30

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
    # Every order older than a minute has been charged or failed: none was dropped.
    stale = conn.execute(
        "SELECT count(*) FROM public.orders"
        " WHERE status = 'pending' AND created_at < now() - interval '60 seconds'"
    ).fetchone()

print(json.dumps({"paid_within_s": paid_within, "stale_pending": stale[0] if stale else None}))
