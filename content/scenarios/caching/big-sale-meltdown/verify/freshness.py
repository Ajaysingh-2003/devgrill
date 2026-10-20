"""Invariant: a price change shows on the product page within seconds.

Runs in the verifier's probe container. Warms the cache with a hot product, changes its price
through the API, then polls the page. Prints {"visible_after_s": seconds or null}.
"""

import json
import os
import random
import time

import httpx

TARGET = os.environ["TARGET"]
PRODUCT = 1043
DEADLINE_S = 15

with httpx.Client(base_url=TARGET, timeout=5) as client:
    for _ in range(3):  # make sure it is cached, whatever the cache does
        client.get(f"/products/{PRODUCT}")
    before = client.get(f"/products/{PRODUCT}").json()["price_cents"]
    new_price = before + random.randint(1, 500)
    client.put(f"/products/{PRODUCT}/price", json={"price_cents": new_price}).raise_for_status()
    changed = time.monotonic()
    seen = None
    while time.monotonic() - changed < DEADLINE_S:
        if client.get(f"/products/{PRODUCT}").json().get("price_cents") == new_price:
            seen = round(time.monotonic() - changed, 3)
            break
        time.sleep(0.25)

print(json.dumps({"visible_after_s": seen}))
