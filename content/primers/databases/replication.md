## What it is

Replication copies changes from a primary database to one or more replicas. Applications often send writes to the primary and reads to replicas to spread load. Postgres streaming replication is asynchronous by default: a replica applies changes a little after the primary commits them. That gap is replication lag.

Lag is normally milliseconds. Under heavy writes, a long-running query on the replica, a network problem or a slow disk, it can grow to seconds or minutes. Then reads from a replica return old data, and features that write then immediately read back start to behave strangely.

## How it shows up in an incident

- Users see stale data: an order they just placed is missing, a setting they just changed reverts on refresh.
- Bugs that only happen sometimes, depending on which replica served the read.
- Replica lag graphs climbing during a backfill, a big migration or a traffic spike.
- Disk filling on the primary because WAL is retained for a replica that has fallen behind or disconnected.
- After a failover, recent writes may be missing if they hadn't reached the new primary.

## How to confirm it

On the primary, see how far each replica is behind:

```sql
select client_addr, state, write_lag, flush_lag, replay_lag
from pg_stat_replication;
```

On a replica, see how old the latest applied change is:

```sql
select now() - pg_last_xact_replay_timestamp() as replay_delay;
```

Check whether a replication slot is holding back WAL on the primary:

```sql
select slot_name, active,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) as retained
from pg_replication_slots;
```

## How to get it working again

- **Send read-after-write traffic to the primary** for the affected features, so users see their own changes.
- **Pause the backfill or batch job** that is generating heavy writes.
- **Take a lagging replica out of the read pool** until it catches up.
- **Cancel long queries on the replica** that block replay, if hot standby conflicts are holding it back.

Promoting a lagging replica during a failover can lose the writes it hadn't received. Know how far behind it is before you promote it.

## How to fix it properly

- Route reads by consistency need: anything a user just changed reads from the primary, or waits until the replica has caught up to a known position.
- Throttle backfills and big data changes, and watch lag while they run.
- Alert on replication lag and on WAL retained by slots, and drop slots that are no longer used.
- Use synchronous replication only where losing a committed write is unacceptable, and accept its latency cost.
- Practise failover so you know how much data is at risk.

## Common traps

- **Assuming replicas are always current** and reading from them right after a write.
- **Adding more replicas** to fix lag caused by write volume on the primary.
- **Leaving an unused replication slot** that keeps WAL forever and fills the primary's disk.
- **Failing over to the most lagged replica** without checking its position.
