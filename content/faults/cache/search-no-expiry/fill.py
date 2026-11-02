"""The weekend's searches (fault data): results cached with no expiry, piling up until Valkey
is within about a megabyte of maxmemory. Runs in the tools container, straight to Valkey."""

import json
import random

import redis

HEADROOM = 1_000_000
WORDS = [
    "waterproof",
    "hiking",
    "boots",
    "camping",
    "stove",
    "kids",
    "rain",
    "jacket",
    "wireless",
    "earbuds",
    "coffee",
    "grinder",
    "standing",
    "desk",
    "lamp",
    "yoga",
    "mat",
    "travel",
    "adapter",
    "phone",
    "charger",
    "running",
    "shorts",
    "winter",
    "gloves",
    "ceramic",
    "mug",
    "laptop",
    "sleeve",
    "duffel",
    "bag",
    "cast",
    "iron",
    "pan",
    "noise",
    "cancelling",
    "headset",
    "sale",
    "gift",
]

client = redis.Redis(host="redis-db", port=6379, socket_timeout=10)
target = int(client.config_get("maxmemory")["maxmemory"]) - HEADROOM
rng = random.Random(1042)


def results(n: int) -> str:
    return json.dumps(
        [
            {
                "id": rng.randint(1, 18402),
                "sku": f"SKU-{rng.randint(1, 18402):06d}",
                "name": " ".join(rng.choice(WORDS) for _ in range(3)).title(),
                "price_cents": rng.randint(499, 19999),
                "category": rng.choice(["outdoors", "audio", "kitchen", "home", "office"]),
            }
            for _ in range(n)
        ]
    )


VALUES = [results(rng.randint(8, 20)) for _ in range(300)]
while True:
    left = target - int(client.info("memory")["used_memory"])
    if left <= 0:
        break
    pipe = client.pipeline(transaction=False)
    for _ in range(max(1, min(500, left // 2500))):
        words = " ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 4)))
        pipe.set(f"search:20:{words} {rng.randint(1, 10**9)}", rng.choice(VALUES))
    if any(isinstance(r, Exception) for r in pipe.execute(raise_on_error=False)):
        break
print(f"search cache filled: {client.dbsize()} keys, {client.info('memory')['used_memory_human']}")
