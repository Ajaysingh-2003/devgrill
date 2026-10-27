## What it is

An index lets Postgres find rows without reading the whole table. Without one, a query that filters or sorts on a column does a sequential scan: it reads every row, checks each one, and throws most away. On a small table that is fine. On a table with millions of rows, the same query goes from a millisecond to seconds, and it burns CPU and disk on every call.

Incidents usually start when something changes underneath a query: the table grows past a tipping point, a new query ships without an index, a migration drops or rebuilds an index, or the planner's statistics go stale and it picks a bad plan.

## How it shows up in an incident

- p99 latency on one or two endpoints climbs while others stay normal.
- Database CPU rises steadily with traffic, even though request volume hasn't changed much.
- Disk read throughput goes up as the same table is scanned again and again.
- The connection pool fills because each query holds its connection longer, so unrelated requests start waiting too.
- Slow-query logs fill with the same query shape.

## How to confirm it

Find the statements that cost the most time in total:

```sql
select query, calls, mean_exec_time, total_exec_time
from pg_stat_statements
order by total_exec_time desc
limit 5;
```

Then look at the plan for the suspect query. A `Seq Scan` on a large table, with a filter that discards most rows, is the signature:

```sql
explain (analyze, buffers)
select * from orders where customer_id = 42 order by created_at desc limit 20;
```

Check which tables are scanned sequentially the most:

```sql
select relname, seq_scan, seq_tup_read, idx_scan
from pg_stat_user_tables
order by seq_tup_read desc
limit 5;
```

## How to get it working again

- **Roll back** the deploy that introduced the slow query, if there is one. This is usually the fastest, safest move.
- **Create the missing index concurrently** so you don't block writes:

```sql
create index concurrently idx_orders_customer_created
  on orders (customer_id, created_at desc);
```

`CREATE INDEX CONCURRENTLY` takes longer and can't run inside a transaction, but it doesn't lock the table against writes. A plain `CREATE INDEX` on a busy table can turn a slow incident into an outage.

- **Run `ANALYZE`** on the table if the plan looks wrong because statistics are stale.
- **Shed or cache** the heaviest read path temporarily if the index will take a long time to build.

## How to fix it properly

- Index for the queries you actually run: the filter columns first, then the sort column. Multi-column order matters.
- Review query plans as part of code review for any new query on a large table.
- Keep `pg_stat_statements` on, and alert on new entries near the top by total time.
- Test migrations against production-sized data, so a dropped or rebuilt index is caught before release.
- Remove unused indexes too. Every index slows writes and takes memory.

## Common traps

- **Scaling the database up** to absorb a full table scan. It buys time and money, not a fix.
- **Running `CREATE INDEX` without `CONCURRENTLY`** on a live table and blocking every write behind it.
- **Adding an index per column** instead of one composite index that matches the query.
- **Trusting `EXPLAIN` without `ANALYZE`**: the estimated plan can differ from what really runs.
