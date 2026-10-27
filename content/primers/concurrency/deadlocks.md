## What it is

A deadlock happens when two transactions each hold a lock the other needs. Transaction A locks row 1 and wants row 2. Transaction B locks row 2 and wants row 1. Neither can continue. Postgres detects this after a short wait (`deadlock_timeout`, one second by default), picks one transaction as the victim and aborts it with an error, so the other can finish.

Deadlocks usually come from code that touches the same rows in different orders: one path updates the order then the inventory, another updates the inventory then the order. Under low load they never meet. Under real concurrency, they collide.

## How it shows up in an incident

- Errors in logs: "deadlock detected", with details of the two processes and the locks involved.
- A rise in failed transactions or 500s that clusters around busy periods or batch jobs.
- Retries that sometimes succeed, so the error rate is noisy rather than constant.
- Latency spikes of about a second, the deadlock detection wait, before each failure.

## How to confirm it

Postgres logs every deadlock with the two statements involved. Search for them:

```sh
grep -A6 'deadlock detected' postgres.log | head -40
```

The database also counts them:

```sql
select datname, deadlocks from pg_stat_database where datname = current_database();
```

Check it twice a few minutes apart to see whether the count is climbing. While it is happening, look at who is waiting on whom:

```sql
select pid, pg_blocking_pids(pid) as blocked_by, wait_event, left(query, 80)
from pg_stat_activity
where wait_event_type = 'Lock';
```

Then read the code paths for the two statements in the log and note the order in which each one touches tables and rows.

## How to get it working again

- **Retry the aborted transaction**: a deadlock victim can usually be retried safely if the transaction is idempotent, and the retry often succeeds.
- **Pause the batch job** that collides with live traffic, and run it off-peak or in smaller batches.
- **Roll back** a change that introduced a new path touching rows in a different order.

## How to fix it properly

- Always lock rows and tables in the same order everywhere, for example by sorting IDs before updating several rows.
- Keep transactions short and touch as few rows as possible.
- Lock up front with `select ... for update` in a consistent order, rather than discovering locks halfway through.
- Process batch updates in small chunks, so each transaction holds few locks.
- Retry deadlock errors automatically, a limited number of times, at the transaction level.

## Common traps

- **Raising `deadlock_timeout`**, which only makes each deadlock take longer to resolve.
- **Retrying without fixing the order**, so the error rate stays high under load.
- **Long transactions that do slow work** such as HTTP calls while holding row locks.
- **Treating deadlocks as random noise** when they point at a specific pair of code paths.
