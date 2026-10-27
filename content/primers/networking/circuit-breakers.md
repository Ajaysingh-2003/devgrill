## What it is

A circuit breaker protects a service from a failing dependency. It watches calls to that dependency. While things are healthy, the breaker is closed and calls go through. When failures or timeouts pass a threshold, it opens: for a while, calls fail immediately without reaching the dependency. After a cool-down it goes half-open and lets a few trial calls through. If they succeed, it closes again; if not, it opens again.

The point is to fail fast. Without a breaker, every request waits for a timeout on a dependency that is clearly down, tying up workers and connections, and the retries keep hammering the dependency so it can't recover.

## How it shows up in an incident

- Without a breaker: latency on many endpoints climbs to the timeout of one dependency, workers fill up, and the slowdown spreads to services that barely use it.
- With a breaker that's working: errors for one feature appear quickly and cleanly, while the rest of the service stays fast.
- With a badly tuned breaker: it flaps open and closed, or opens on a few harmless errors and blocks a healthy dependency.
- Logs and metrics show breaker state changes: "circuit open for payments".

## How to confirm it

Check whether a breaker exists on the slow path, and what state it is in. Many libraries log state changes or expose them as metrics:

```sh
grep -i -E 'circuit (open|half|closed)|breaker' api.log | tail -20
curl -s api:8000/metrics | grep -i breaker
```

If there is no breaker, look at how long calls to the failing dependency take and whether workers are waiting on them:

```sh
time curl -s -o /dev/null payments:8080/health
py-spy dump --pid 1234
```

## How to get it working again

- **Open the breaker manually**, or disable the feature through a flag, so calls stop immediately.
- **Serve a fallback**: cached data, a default value, or a clear message that one feature is unavailable.
- **Shorten timeouts** on the failing dependency while it recovers.
- **Close the breaker gradually** once the dependency is healthy, so it isn't flooded on recovery.

## How to fix it properly

- Put a breaker around every remote dependency that can fail independently, especially optional ones.
- Base thresholds on error rate over a time window, with a minimum number of calls, so a few errors don't trip it.
- Decide what each feature does when its breaker is open: a fallback, a degraded response, or a fast, clear error.
- Combine with timeouts, bounded retries and separate connection pools per dependency.
- Expose breaker state in dashboards and alert when one opens.
- Test it: make a dependency fail in staging and check that the rest of the service stays healthy.

## Common traps

- **Thresholds so sensitive** that the breaker opens on normal noise and blocks a healthy service.
- **No fallback**, so an open breaker turns into errors on pages that could have degraded gracefully.
- **One breaker for many dependencies**, so one failure blocks unrelated calls.
- **Retries inside the breaker** that make each call slow before it fails.
