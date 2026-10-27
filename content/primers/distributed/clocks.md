## What it is

Every server has its own clock, and no two clocks agree exactly. NTP keeps them close, usually within milliseconds, but clocks can drift, jump forward or backward when they resync, or be badly wrong on a machine that lost its time sync. Code that assumes all clocks agree, or that time only moves forward, breaks in subtle ways.

Clock problems show up wherever time decides something: token and certificate expiry, cache TTLs, "last write wins" conflict resolution, rate limits, scheduled jobs, ordering events from different machines, and measuring durations with wall-clock time.

## How it shows up in an incident

- Authentication failures such as "token not yet valid" or "token expired" on some servers only.
- TLS errors like "certificate is not yet valid" after a machine's clock jumps.
- Data that goes backwards: a newer update overwritten by an older one in "last write wins" logic.
- Scheduled jobs running twice, or not at all, around a clock change or daylight saving time.
- Negative durations or wildly wrong timings in logs and metrics.

## How to confirm it

Compare the time on the affected machine with a trusted source and with a healthy machine:

```sh
date -u
timedatectl status
chronyc tracking
```

Look for "System clock synchronized: no", or a large offset. Compare timestamps for the same event recorded by two services. If they disagree by seconds, clocks are skewed.

Check the database's view of time against the application server's:

```sql
select now(), clock_timestamp();
```

## How to get it working again

- **Resync the clock** on the bad machine and make sure the time sync service is running.
- **Take the skewed machine out of rotation** until its clock is right.
- **Widen tolerances temporarily**, for example token validation leeway of a minute or two, while the fix rolls out.
- **Re-run or repair** jobs that ran twice or were skipped.

A large backwards jump can itself cause errors in running processes, so restarting affected services after a resync is often sensible.

## How to fix it properly

- Run time sync everywhere and alert when a machine loses sync or drifts.
- Use monotonic clocks for measuring durations and timeouts, never wall-clock time (`time.monotonic()` in Python).
- Store and compare timestamps in UTC, and handle time zones and daylight saving only for display.
- Allow small clock skew when validating tokens and certificates.
- Don't decide ordering by comparing timestamps from different machines. Use version numbers, sequence IDs or a single source of truth.
- Schedule jobs with idempotency so a duplicate run does no harm.

## Common traps

- **Assuming clocks agree across machines**, especially for ordering writes.
- **Measuring durations with wall-clock time**, which jumps when clocks resync.
- **Local time in storage**, which breaks around daylight saving changes.
- **Zero tolerance on token expiry**, so a tiny skew locks users out.
