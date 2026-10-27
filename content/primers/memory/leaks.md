## What it is

A memory leak is memory the program keeps holding but no longer needs. In garbage-collected languages like Python, a leak is usually a reference that never goes away: a module-level cache or dict that only grows, a list that collects every request, objects stuck in a reference cycle with resources attached, or a C extension that allocates and never frees.

The process grows a little with every request until it hits a limit. In a container, the kernel's out-of-memory killer ends it, the orchestrator restarts it, and the cycle starts again. That's why leaks often look like "the service restarts every few hours" rather than a crash with a clear error.

## How it shows up in an incident

- Memory per process climbs in a steady line, then drops suddenly at a restart: a sawtooth graph.
- Containers restart with exit code 137 or an `OOMKilled` reason.
- Latency gets worse as memory grows, from garbage collection or swapping, then recovers after each restart.
- The restart interval shortens when traffic rises, because each request leaks a little.
- It started with a deploy that added caching, a new library, or a new code path.

## How to confirm it

Check whether the process was killed for memory:

```sh
docker inspect api --format '{{.State.OOMKilled}} {{.RestartCount}}'
dmesg | grep -i 'killed process' | tail
```

Watch memory over time for one process:

```sh
ps -o pid,rss,etime,cmd -C python
```

Run it a few minutes apart. If resident memory (RSS) grows with traffic and never comes back down, it's a leak rather than a normal warm-up.

In Python, `tracemalloc` compares snapshots and shows which lines allocate the memory that keeps growing. Many services expose it behind a debug endpoint, or you can enable it in a staging copy and replay traffic.

## How to get it working again

- **Roll back** the deploy that introduced the growth. This is the fastest fix when the timing lines up.
- **Restart on a schedule**, or lower the worker's max requests setting (for example `--max-requests` in Gunicorn), so processes are recycled before they run out of memory. This buys time, it doesn't fix the leak.
- **Raise the memory limit** temporarily if restarts are hurting users, while you find the cause.

## How to fix it properly

- Find the growing objects with `tracemalloc` or a heap profiler, and fix the reference that keeps them alive.
- Give every in-process cache a size limit and an eviction policy, for example `functools.lru_cache(maxsize=...)`.
- Close resources explicitly: files, sockets, database sessions, and clear per-request state.
- Alert on memory growth rate and on restart counts, not just on memory near the limit.
- Load-test long enough to see growth, hours rather than minutes.

## Common traps

- **Only raising the memory limit**, which makes each restart rarer but bigger.
- **Blaming the garbage collector** when the code still holds references.
- **Unbounded caches** like a plain dict keyed by user or request.
- **Treating regular restarts as normal behaviour** and losing in-flight work each time.
