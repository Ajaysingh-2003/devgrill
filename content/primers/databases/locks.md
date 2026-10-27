## What it is

Postgres takes locks to keep concurrent changes consistent. Most are invisible: a row being updated locks just that row for a moment. Trouble starts when a session takes a strong lock on a whole table, or holds a lock for a long time, and everything else queues behind it.

The classic incident is a lock queue. A migration runs `ALTER TABLE` and needs an `ACCESS EXCLUSIVE` lock. It waits for one long-running query to finish. Meanwhile every new query on that table, even a simple `SELECT`, queues behind the waiting `ALTER`. One slow transaction plus one DDL statement can freeze a table for every request.

## How it shows up in an incident

- One or more endpoints hang at the same moment, often right after a deploy or a scheduled job.
- Requests time out, while database CPU stays low: everyone is waiting, nobody is working.
- The connection pool fills with connections stuck on the blocked table.
- Logs show "canceling statement due to lock timeout" or statement timeouts.

## How to confirm it

Find who is waiting, and on whom:

```sql
select pid, wait_event_type, wait_event, state,
       pg_blocking_pids(pid) as blocked_by,
       now() - query_start as waiting_for, left(query, 80) as query
from pg_stat_activity
where wait_event_type = 'Lock'
order by waiting_for desc;
```

Then look at the blocker itself, the session at the head of the queue:

```sql
select pid, state, now() - xact_start as in_tx, left(query, 120)
from pg_stat_activity
where pid = 12345;
```

`pg_locks` shows the lock modes held and requested if you need more detail:

```sql
select locktype, relation::regclass, mode, granted, pid
from pg_locks
where not granted;
```

## How to get it working again

- **Cancel the blocker** if it is safe to do so: `select pg_cancel_backend(pid);`. If it doesn't stop, `pg_terminate_backend(pid)` ends the session.
- **Stop the migration or job** that is holding or waiting for the strong lock. Rolling back the deploy that started it is often the cleanest path.
- **Retry the migration later**, at a quiet time, with a short `lock_timeout` so it gives up instead of blocking traffic.

Before killing a session, check what it is doing. Terminating a long data fix halfway rolls back all of its work.

## How to fix it properly

- Set `lock_timeout` for migrations (for example 5 seconds) so DDL fails fast instead of queueing everyone.
- Use non-blocking migration patterns: `CREATE INDEX CONCURRENTLY`, add nullable columns, backfill in batches, add constraints as `NOT VALID` and validate separately.
- Keep transactions short in application code, and set `idle_in_transaction_session_timeout`.
- Alert on lock waits and on transactions open longer than a few minutes.

## Common traps

- **Restarting the database** to clear locks. It drops every connection and in-flight write, and the migration may simply run again.
- **Killing the waiting `ALTER`** but not the long transaction ahead of it, so the next migration repeats the outage.
- **Adding a column with a volatile default** on a big table, forcing a full rewrite under lock.
- **Assuming low CPU means the database is healthy**: lock waits use no CPU.
