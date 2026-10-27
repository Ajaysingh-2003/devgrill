## What it is

A cache has a memory limit. When it is full and a new value arrives, it must throw something out. That is eviction. Redis uses the `maxmemory` setting and a `maxmemory-policy`, such as `allkeys-lru` (remove the least recently used key) or `volatile-ttl` (remove keys closest to expiry). With `noeviction`, Redis refuses new writes instead.

Eviction is normal in a healthy cache. It becomes an incident when the working set no longer fits: memory is too small for the traffic, values grew, a new feature caches much more, or a few large keys crowd everything else out. Keys are evicted before they are read again, the hit rate drops, and the database takes the load.

## How it shows up in an incident

- Cache hit rate falls gradually under load, then database reads rise to match.
- Redis memory sits flat at its limit, and the evicted keys counter climbs quickly.
- Latency gets worse at peak times and recovers when traffic drops.
- With `noeviction`, writes to Redis start failing with "OOM command not allowed when used memory > maxmemory".
- A recent deploy started caching bigger objects, or caching something new.

## How to confirm it

Check memory against the limit, the policy, and how fast keys are being evicted:

```sh
redis-cli -h redis INFO memory | grep -E 'used_memory_human|maxmemory_human|maxmemory_policy'
redis-cli -h redis INFO stats | grep -E 'evicted_keys|keyspace_(hits|misses)'
```

Run the stats command twice a minute apart: a rising `evicted_keys` count alongside a falling hit ratio is the signature.

Find what is taking the space:

```sh
redis-cli -h redis --bigkeys
redis-cli -h redis MEMORY USAGE product:1042
```

## How to get it working again

- **Raise `maxmemory`** if the host has room. This is a reasonable short-term fix when the working set simply outgrew the limit.
- **Remove or shrink the large keys** that are crowding out everything else.
- **Roll back** a change that started caching much larger values.
- **Check the policy**: if it is `noeviction` and writes are failing, the application may be erroring on every cache write.

Raising the limit past the machine's real memory leads to swapping or the process being killed, which is worse than evictions.

## How to fix it properly

- Size the cache from the working set: how much of the data is read often enough to be worth keeping.
- Cache only what is read often, store compact values, and give every key a TTL.
- Choose an eviction policy that matches how keys are used. `allkeys-lru` suits most read caches.
- Alert on eviction rate and hit rate, not only on memory usage.
- Review new caching code for value size and key count.

## Common traps

- **Treating memory at 100% as the problem**: a full cache is normal, a falling hit rate is the signal.
- **Caching everything** with no TTL and letting cold data crowd out hot data.
- **Using `noeviction`** for a cache and turning a full cache into failed writes.
- **Ignoring value size growth** after a schema or serialisation change.
