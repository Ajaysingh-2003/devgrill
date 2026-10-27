## What it is

Opening a Postgres connection is expensive, so applications keep a pool of open connections and lend one to each request while it talks to the database. A pool has a fixed size, and Postgres has a hard limit on total connections (`max_connections`). When every connection in the pool is busy, new requests wait in a queue. If they wait too long, they fail with a timeout or a "pool exhausted" error.

The key idea is Little's law: connections in use = requests per second × time each request holds a connection. Pool exhaustion usually isn't caused by more traffic. It's caused by each request holding its connection longer: slower queries, a slower network path to the database, long transactions, or code that does slow work (an HTTP call, a file upload) while holding a connection.

## How it shows up in an incident

- Latency jumps, often to roughly the pool's wait timeout, and errors like "pool exhausted", "QueuePool limit reached" or "could not obtain connection" appear in logs.
- The database itself looks bored: low CPU, few active queries.
- Connections in use sit at the pool maximum, while connections shown as `idle in transaction` may be high.
- Adding more app replicas makes it worse, because Postgres runs out of connection slots.

## How to confirm it

See what the database's connections are actually doing:

```sql
select state, count(*)
from pg_stat_activity
where datname = current_database()
group by state;
```

Many `idle in transaction` connections means code is holding transactions open. Many `active` ones with long durations means slow queries:

```sql
select pid, state, now() - xact_start as in_tx, left(query, 80)
from pg_stat_activity
where state <> 'idle'
order by in_tx desc nulls last
limit 10;
```

Measure how long a trivial query takes from the app's side. If `select 1` takes 100+ ms, the problem is the path to the database, not the database:

```sh
time psql "$DATABASE_URL" -c 'select 1'
```

## How to get it working again

- **Roll back** the change that made each request hold its connection longer: a config change, a new slow query, a new network hop.
- **Kill runaway sessions** that hold connections or locks for minutes (`pg_terminate_backend(pid)`), after checking what they are.
- **Shed load** on the most expensive endpoint so the rest of the service recovers.

Raising the pool size is a temporary measure at best. If the database is idle and requests are waiting, a bigger pool just means more connections waiting on the same slow path, and it can exhaust `max_connections` for everyone.

## How to fix it properly

- Keep transactions short. Never hold a connection while calling another service.
- Set sensible timeouts: a pool wait timeout, a statement timeout, and `idle_in_transaction_session_timeout`.
- Size pools from the math: replicas × pool size must stay well under `max_connections`. Consider a pooler like PgBouncer.
- Alert on pool wait time and on client-side query latency, not just database CPU.
- Review config changes to database endpoints like code changes.

## Common traps

- **Scaling the database** when its CPU is low. The bottleneck is the time connections are held.
- **Doubling the pool size** and blowing through `max_connections`.
- **Adding app replicas**, which multiplies the connections asked of Postgres.
- **Looking only at database metrics**: the slowness is visible from the client side.
