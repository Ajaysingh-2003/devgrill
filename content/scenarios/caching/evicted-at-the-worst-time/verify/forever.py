"""Invariant: what the app caches for a search can expire, so the cache can make room.

Runs in the verifier's probe container with TARGET (the API) and CACHE_HOST (Valkey). Sends 30
searches tagged with a fresh marker, then finds every Valkey key that carries the marker and
counts those with no TTL. Prints {"forever_keys": n, "cached_keys": n}. An app that doesn't
cache searches at all passes.
"""

import json
import os
import random
import secrets

import httpx
import redis

TARGET = os.environ["TARGET"]
cache = redis.Redis(host=os.environ["CACHE_HOST"], port=6379, socket_timeout=10)
marker = f"dg{secrets.token_hex(6)}"
rng = random.Random()

with httpx.Client(base_url=TARGET, timeout=10) as client:
    for n in range(30):
        query = f"{rng.choice(['trail', 'urban', 'pro'])} kettle {marker}{n}"
        client.get("/products", params={"q": query, "limit": 10})

keys = list(cache.scan_iter(match=f"*{marker}*", count=5000))
forever = sum(cache.ttl(key) == -1 for key in keys)
print(json.dumps({"forever_keys": forever, "cached_keys": len(keys)}))
