## What it is

A schema migration changes the shape of the database while the application keeps running: adding a column, an index, a constraint, or reshaping data. Migrations are risky because they touch shared state that every request depends on, and because old and new versions of the code run side by side during a deploy.

Most migration incidents fall into a few patterns: a statement that locks a busy table, a statement that rewrites a big table, a backfill that hammers the database, or a change that the old version of the code can't handle.

## How it shows up in an incident

- Errors or timeouts start right as a deploy or migration job begins.
- A single table becomes unusable: queries on it hang while the rest of the app works.
- Disk I/O and write-ahead log volume spike during a table rewrite, and replicas fall behind.
- After the deploy, old pods throw errors like "column does not exist" or "null value violates not-null constraint".

## How to confirm it

Check whether a migration is running, and whether it is waiting or blocking:

```sql
select pid, state, wait_event_type, now() - query_start as running_for,
       pg_blocking_pids(pid) as blocked_by, left(query, 100)
from pg_stat_activity
where query ilike '%alter table%' or query ilike '%create index%';
```

See how much is queued behind it:

```sql
select count(*) from pg_stat_activity where wait_event_type = 'Lock';
```

Look at the deploy and migration history to line up the start of the errors with a specific change:

```sh
git log --oneline -5
git show HEAD -- migrations/
```

## How to get it working again

- **Stop the migration** if it is blocking traffic: cancel its session, then pause the deploy.
- **Roll back the application** if the new code needs a schema that isn't there, or the old code breaks on the new schema.
- **Pause the backfill** and restart it with smaller batches and a sleep between them.

Rolling back a schema change is often harder than rolling back code. Dropping a column that new writes already use can lose data. When in doubt, roll back the code and leave the schema alone.

## How to fix it properly

- Follow expand and contract: add the new structure, deploy code that writes both, backfill, switch reads, then remove the old structure in a later release.
- Make every step safe for the version before and after it.
- Use `lock_timeout` and retry, `CREATE INDEX CONCURRENTLY`, nullable columns, and constraints added as `NOT VALID` then validated.
- Backfill in batches of a few thousand rows, with progress logging and a way to stop.
- Test migrations against a copy of production-sized data and time them.

## Common traps

- **Renaming or retyping a column in one step** while old code still reads it.
- **Adding `NOT NULL` with a default** on a huge table and triggering a rewrite.
- **Running one giant `UPDATE`** for a backfill and bloating the table and replicas.
- **Rolling back the schema in a panic** and losing data written by the new code.
