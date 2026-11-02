"""Invariant: a shopper who signs in stays signed in while the cache is busy, and a made-up
session is never accepted.

Runs in the verifier's probe container with TARGET (the API). Signs in 30 shoppers, browses
200 product pages and 100 new searches (cache writes), then checks every shopper is still
signed in as themselves. Prints {"lost": n, "fake_accepted": n}: shoppers who couldn't sign
in or were signed out, and made-up tokens the API accepted.
"""

import json
import os
import random
import secrets

import httpx

TARGET = os.environ["TARGET"]
rng = random.Random()
lost = fake = 0

with httpx.Client(base_url=TARGET, timeout=10) as client:
    shoppers = {}
    for user in rng.sample(range(1, 2001), 30):
        res = client.post("/sessions", json={"user_id": user})
        token = res.json().get("token") if res.status_code == 201 else None
        if token:
            shoppers[user] = token
        else:
            lost += 1
    for _ in range(200):
        client.get(f"/products/{rng.randint(1, 18402)}")
    for _ in range(100):
        client.get("/products", params={"q": f"pro lamp {rng.randint(1, 10**6)}", "limit": 10})
    for user, token in shoppers.items():
        res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        if res.status_code != 200 or res.json().get("user_id") != user:
            lost += 1
    for _ in range(5):
        res = client.get("/me", headers={"Authorization": f"Bearer {secrets.token_urlsafe(24)}"})
        fake += res.status_code != 401

print(json.dumps({"lost": lost, "fake_accepted": fake}))
