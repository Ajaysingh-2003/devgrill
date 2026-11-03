"""Invariant: a shopper sees their own order the moment it is placed.

Runs in the verifier's probe container with TARGET (the API). Places 20 orders; right after
each, opens its order page and the shopper's order history. Prints {"missing_pages": n,
"missing_in_history": n}: orders their own shopper couldn't see.
"""

import json
import os
import random

import httpx

TARGET = os.environ["TARGET"]
missing_pages = missing_in_history = 0

with httpx.Client(base_url=TARGET, timeout=10) as client:
    for _ in range(20):
        user = random.randint(1, 2000)
        res = client.post(
            "/orders",
            json={"user_id": user, "product_id": random.randint(1, 18402), "quantity": 1},
        )
        res.raise_for_status()
        order_id = res.json()["id"]
        page = client.get(f"/users/{user}/orders/{order_id}")
        if page.status_code != 200 or page.json().get("id") != order_id:
            missing_pages += 1
        history = client.get(f"/users/{user}/orders")
        if history.status_code != 200 or order_id not in [o.get("id") for o in history.json()]:
            missing_in_history += 1

print(json.dumps({"missing_pages": missing_pages, "missing_in_history": missing_in_history}))
