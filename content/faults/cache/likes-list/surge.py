"""The night the film star posted (fault data): product 4242 collects 600,000 likes, from
fans 100,000 to 699,999 (the oldest at the tail of the list, the newest at its head)."""

import redis

client = redis.Redis(host="redis-db", port=6379, socket_timeout=30)
KEY = "likes:list:4242"
client.delete(KEY)
for start in range(100_000, 700_000, 20_000):
    client.lpush(KEY, *range(start, start + 20_000))
print(f"{KEY}: {client.llen(KEY)} likes, {client.memory_usage(KEY)} bytes")
