"""Invariant: every order is charged exactly once while the payment provider is slow.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN (read-only). Gives the
provider its slow afternoon (one charge in ten takes a second), places 40 orders over 10
seconds, waits up to 40 seconds for them to be paid, then asks the provider for each order's
charges. Prints {"duplicates": orders charged more than once, "unpaid": orders not paid}.
"""

import json
import os
import random
import time

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
PROVIDER = "http://payment-gateway:8080"
CONTROL = "http://payment-gateway:8081/_config"
ORDERS = 40
DEADLINE_S = 40

httpx.post(CONTROL, json={"slow_share": 0.1, "slow_ms": 1000, "latency_ms": 10}, timeout=5)
ids = []
with httpx.Client(base_url=TARGET, timeout=5) as client:
    for _ in range(ORDERS):
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
        time.sleep(0.25)
placed = time.monotonic()

unpaid = len(ids)
with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    while time.monotonic() - placed < DEADLINE_S:
        row = conn.execute(
            "SELECT count(*) FROM public.orders WHERE id = ANY(%s) AND status <> 'paid'", (ids,)
        ).fetchone()
        unpaid = row[0] if row else len(ids)
        if unpaid == 0:
            break
        time.sleep(0.5)
time.sleep(2)  # a charge the worker gave up on lands up to a second later

with httpx.Client(base_url=PROVIDER, timeout=5) as provider:
    charges = [len(provider.get("/charges", params={"order_id": i}).json()) for i in ids]
print(json.dumps({"duplicates": sum(n > 1 for n in charges), "unpaid": unpaid, "orders": len(ids)}))
