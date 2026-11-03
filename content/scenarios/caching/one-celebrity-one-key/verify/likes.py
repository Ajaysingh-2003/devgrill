"""Invariant: the like button tells the truth on the viral product.

Runs in the verifier's probe container with TARGET (the API). On product 4242: a fan who liked
it the night it went viral (the oldest like) and one of the latest must show as liked, a
shopper who never liked it must not, and a new like must show at once and add one to the
count. Prints {"wrong": number of wrong answers}.
"""

import json
import os
import random

import httpx

TARGET = os.environ["TARGET"]
PRODUCT = 4242
wrong = 0


def likes(client: httpx.Client, user: int) -> tuple[bool | None, int]:
    res = client.get(f"/products/{PRODUCT}/likes", params={"user_id": user})
    if res.status_code != 200:
        return None, -1
    body = res.json()
    return body.get("liked"), int(body.get("count", -1))


with httpx.Client(base_url=TARGET, timeout=10) as client:
    for user, expected in ((100_000, True), (699_999, True), (9_999_999, False)):
        if likes(client, user)[0] is not expected:
            wrong += 1
    newcomer = random.randint(10_000_000, 99_999_999)
    _, before = likes(client, newcomer)
    res = client.post(f"/products/{PRODUCT}/likes", json={"user_id": newcomer})
    mine, after = likes(client, newcomer)
    if res.status_code != 201 or mine is not True or after != before + 1:
        wrong += 1

print(json.dumps({"wrong": wrong}))
