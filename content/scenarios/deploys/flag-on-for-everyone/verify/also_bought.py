"""Invariant: whenever the "customers also bought" box is shown, it lists real co-purchases.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN (read-only). Asks for
the box on the popular products for a spread of users. Every list that is shown must be non-empty
when the product has co-purchases, and name only products its customers really bought. Prints
{"wrong_lists": count, "shown": count}. A rollout of 0% (nothing shown) passes.
"""

import json
import os

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
PRODUCTS = [3001, 3002, 3003, 3004, 3005]  # the scenario's HOT_KEYS
USERS = range(1, 201, 7)

CO_BOUGHT = (
    "SELECT DISTINCT o2.product_id FROM public.orders o1"
    " JOIN public.orders o2 ON o2.user_id = o1.user_id AND o2.product_id <> o1.product_id"
    " WHERE o1.product_id = %s"
)

wrong = shown = 0
with (
    httpx.Client(base_url=TARGET, timeout=10) as client,
    psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn,
):
    conn.execute("SET search_path = pg_catalog, public")
    real = {p: {r[0] for r in conn.execute(CO_BOUGHT, (p,)).fetchall()} for p in PRODUCTS}
    for product in PRODUCTS:
        for user in USERS:
            res = client.get(f"/products/{product}/also-bought", params={"user_id": user})
            res.raise_for_status()
            body = res.json()
            if not body.get("enabled"):
                continue
            shown += 1
            items = [i.get("product_id") for i in body.get("items", [])]
            if (real[product] and not items) or not set(items) <= real[product]:
                wrong += 1

print(json.dumps({"wrong_lists": wrong, "shown": shown}))
