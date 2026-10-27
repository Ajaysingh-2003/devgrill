## What it is

A cache stampede, also called a thundering herd, happens when many requests miss the cache at the same moment and all go to the database together. Normally the cache absorbs most reads and the database sees a trickle. When a popular key disappears, every request for it misses at once, each one runs the same expensive query, and each one tries to write the result back.

Common triggers: the cache restarts or is flushed, a deploy changes how keys are built, many keys were written at once with the same expiry and now expire together, or one very hot key expires under load.

## How it shows up in an incident

- Cache hit rate drops sharply, then database load spikes within seconds.
- Database CPU and active connections jump, and the same query appears many times at once.
- Latency climbs across endpoints that share the database, not just the one that missed.
- It can feed itself: the database slows down, the cache can't refill, and misses keep coming.
- Graphs often show a sawtooth if many keys expire on the same schedule.

## How to confirm it

Check the cache's hit and miss counters and whether it was recently restarted:

```sh
redis-cli -h redis INFO stats | grep -E 'keyspace_(hits|misses)'
redis-cli -h redis INFO server | grep uptime_in_seconds
```

Look at what the database is busy with. A stampede shows many copies of the same query:

```sql
select left(query, 80) as query, count(*)
from pg_stat_activity
where state = 'active'
group by 1
order by 2 desc;
```

Watch reads and writes for a key you expect to be cached:

```sh
redis-cli -h redis TTL product:1042
redis-cli -h redis MONITOR | head -50
```

## How to get it working again

- **Shed or rate-limit load** on the hot path so the database can recover and the cache can refill.
- **Warm the cache** for the hottest keys before letting full traffic back.
- **Roll back** a deploy that changed key formats or expiry settings.
- **Serve stale data** briefly if the application supports it, rather than hitting the database.

Restarting the cache again in the middle of a stampede empties it and makes things worse.

## How to fix it properly

- **Request coalescing:** only one request per key refills it, the others wait for that result or use the old value. A short lock per key in Redis does this.
- **Jitter expiry times** so keys written together don't expire together.
- **Refresh early:** refresh a hot key shortly before it expires, in the background.
- **Keep the cache warm across restarts** with replicas or persistence, and warm it before a planned event.
- Alert on hit rate drops, not just on database load.

## Common traps

- **Scaling the database** to absorb a stampede that a fix in the cache layer would prevent.
- **Flushing the cache** to "reset" a problem and causing the stampede.
- **Giving every key the same fixed TTL**, which lines up expiries.
- **Retrying failed reads immediately**, which adds even more load to the database.
