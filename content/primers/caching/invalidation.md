## What it is

Invalidation is how a cache learns that the data it holds is out of date. When the source of truth changes, the cached copy must be removed or updated, otherwise readers keep seeing the old value until it expires. There are two common approaches: delete or update the cache entry when the data is written, or let entries expire after a time-to-live (TTL) and accept some staleness.

Incidents come from the gaps: a write path that forgets to invalidate, a race where an old value is written back after a newer one, keys that are built differently on read and write, or a TTL set so long that bad data lingers for hours.

## How it shows up in an incident

- Users see old prices, stock levels or settings, while the database has the right values.
- The problem fixes itself after a while, which is the TTL running out.
- Only some users or some pages are affected, depending on which key or replica they hit.
- Clearing the cache "fixes" it, until it happens again.
- Support tickets arrive before any graph moves, because staleness doesn't hurt latency.

## How to confirm it

Compare the cached value with the source of truth:

```sh
redis-cli -h redis GET product:1042
redis-cli -h redis TTL product:1042
```

```sql
select id, price, updated_at from products where id = 1042;
```

If they differ, find out when the cache entry was written and whether the write path invalidated it. Watching the cache while you update a record shows whether a delete or set happens:

```sh
redis-cli -h redis MONITOR | grep 1042
```

Check that reads and writes build the same key. A key format change on one side means every update misses its target.

## How to get it working again

- **Delete the affected keys** so the next read loads fresh data. Delete narrowly: a targeted pattern, not the whole cache.
- **Roll back** a change that altered key formats or removed an invalidation call.
- **Shorten the TTL** temporarily for the affected data while you fix the write path.

Deleting keys with `KEYS pattern` blocks Redis on a large dataset. Use `SCAN` to find them in batches.

## How to fix it properly

- Invalidate on every write path, including admin tools, background jobs and bulk imports, not just the main API.
- Prefer deleting the key after the database commit over setting a new value, which avoids writing back an old value in a race.
- Version keys when the data shape changes, so old and new code never read each other's entries.
- Keep TTLs as a safety net even for actively invalidated data.
- Test that a write followed by a read returns the new value.

## Common traps

- **Flushing the entire cache** to fix stale data, causing a stampede on the database.
- **Updating the cache before the database commit**, so a rolled-back transaction leaves bad data cached.
- **Forgetting secondary writers** such as batch jobs and admin scripts.
- **Relying only on long TTLs** for data that must be correct, like prices.
