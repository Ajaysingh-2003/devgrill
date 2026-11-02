"""Invariant: after a payment provider outage, the backlog drains and every order is charged.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN (read-only). Sets the
provider's rate limit back to its usual 60 calls a second and takes it down for 15 seconds,
placing 8 orders a second meanwhile and for 10 seconds after. Then waits for every one of them
to be paid. Prints {"recovered_s": seconds from the end of the outage until all were paid (null
if they never were), "unpaid": n}.
"""

import json
import os
import random
import time

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
CONTROL = "http://payment-gateway:8081/_config"
OUTAGE_S = 15
PLACING_S = 25
DEADLINE_S = 60

httpx.post(CONTROL, json={"rate_limit": 60, "down_s": OUTAGE_S}, timeout=5).raise_for_status()
started = time.monotonic()
ids = []
with httpx.Client(base_url=TARGET, timeout=5) as client:
    while time.monotonic() - started < PLACING_S:
        res = client.post(
            "/orders",
            json={
                "user_id": random.randint(1, 2000),
                "product_id": random.randint(1, 18402),
                "quantity": 1,
            },
        )
        if res.status_code == 201:
            ids.append(res.json()["id"])
        time.sleep(0.125)
outage_over = started + OUTAGE_S

recovered = None
unpaid = len(ids)
with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    while time.monotonic() - outage_over < DEADLINE_S:
        row = conn.execute(
            "SELECT count(*) FROM public.orders WHERE id = ANY(%s) AND status <> 'paid'", (ids,)
        ).fetchone()
        unpaid = row[0] if row else len(ids)
        if unpaid == 0:
            recovered = round(time.monotonic() - outage_over, 1)
            break
        time.sleep(0.5)

print(json.dumps({"recovered_s": recovered, "unpaid": unpaid, "placed": len(ids)}))
