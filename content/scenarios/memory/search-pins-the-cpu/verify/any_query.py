"""Invariant: no search query, however odd, holds the API for long.

Runs in the verifier's probe container with TARGET (the API). Sends three search queries
nobody has sent before: a few words of letters ending in punctuation, the shape that makes a
backtracking regex explode. Prints {"slowest_ms": the slowest answer, or null if one didn't
answer within 3 seconds}.
"""

import json
import os
import random
import string
import time

import httpx

TARGET = os.environ["TARGET"]
TIMEOUT_S = 3


def query() -> str:
    words = [
        "".join(random.choices(string.ascii_lowercase, k=random.randint(7, 8))) for _ in range(4)
    ]
    return " ".join(words) + random.choice("!?.,")


slowest: float | None = 0.0
with httpx.Client(base_url=TARGET, timeout=TIMEOUT_S) as client:
    for _ in range(3):
        started = time.monotonic()
        try:
            client.get("/products", params={"q": query(), "limit": 10}).raise_for_status()
        except httpx.TimeoutException:
            slowest = None
            break
        slowest = max(slowest, (time.monotonic() - started) * 1000)

print(json.dumps({"slowest_ms": None if slowest is None else round(slowest, 1)}))
