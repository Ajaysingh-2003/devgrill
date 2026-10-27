## What it is

A hot key is a single cache entry that receives a huge share of the traffic: one viral product, one celebrity profile, one global config value read on every request. Caches spread keys across nodes or CPU time evenly on average, but a single key always lives in one place. When one key gets thousands of requests per second, that node or that Redis process becomes the bottleneck while the rest of the cache sits idle.

Redis runs commands on a single main thread, so one hot key with a large value can saturate it. In a cluster, one shard maxes out while the others are quiet.

## How it shows up in an incident

- Latency rises for everything served by one cache node or shard, while others look healthy.
- Redis CPU on one instance sits near 100%, and network bandwidth from it spikes.
- The spike lines up with a real-world event: a sale, a viral post, a push notification.
- If the cache node falls over, the hot key's traffic moves to the database at once.
- Clients log timeouts from Redis even though memory and connections look fine.

## How to confirm it

Find the busiest keys. On recent Redis versions with an LFU eviction policy, `--hotkeys` samples key frequency:

```sh
redis-cli -h redis --hotkeys
redis-cli -h redis --bigkeys
```

Sample live commands for a few seconds and count keys:

```sh
redis-cli -h redis MONITOR | head -2000 | awk '{print $5}' | sort | uniq -c | sort -rn | head
```

Check CPU and command stats on the busy instance:

```sh
redis-cli -h redis INFO cpu
redis-cli -h redis INFO commandstats | head
```

## How to get it working again

- **Cache the hot value inside the application** for a few seconds. A small in-process cache absorbs most of the reads.
- **Reduce the value size** if the hot key holds a large blob that is fetched on every request.
- **Rate-limit or shed** the endpoint driving the traffic if the cache can't keep up.

Restarting the overloaded node moves the problem to another node, or to the database.

## How to fix it properly

- Add a short-lived local cache in front of the shared cache for known hot data.
- Replicate hot keys: store copies under several suffixed keys and read a random one, so the load spreads across shards.
- Keep values small, and split large objects into the parts each request actually needs.
- Use read replicas for Redis where reads dominate.
- Monitor per-node and per-shard load, not just cluster averages.

## Common traps

- **Adding more cache nodes**: a single key still lives on one of them.
- **Assuming the average load is fine** when one shard is saturated.
- **Fetching a large blob on every request** when only one field is needed.
- **Running `MONITOR` for a long time** on a busy production instance, which itself adds load.
