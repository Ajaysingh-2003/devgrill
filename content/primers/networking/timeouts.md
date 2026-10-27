## What it is

A timeout is how long a caller is willing to wait for an answer before giving up. Every network call needs one: to a database, a cache, another service, a payment provider. Without a timeout, a slow or stuck dependency holds your request, your worker and your connection forever, and its problem becomes yours.

Timeouts have to fit together. If a user's browser waits 30 seconds, the API waits 60 seconds for a service, and that service waits 90 seconds for its database, the outer layers give up while the inner ones keep working on requests nobody is waiting for. Too short is also a problem: a timeout below normal latency fails healthy requests and triggers retries.

## How it shows up in an incident

- Errors such as "timeout", "deadline exceeded", 504 Gateway Timeout or "read timed out".
- Latency graphs flat at a suspicious round number, like exactly 30 seconds: that's a timeout firing.
- Workers or connections pile up waiting on one dependency.
- Retries after timeouts multiply the load on the slow dependency.
- Work completes in the backend after the user has already seen an error, causing duplicates.

## How to confirm it

Find which call is timing out, and how long it waited:

```sh
grep -i -E 'timeout|timed out|deadline' api.log | tail -20
```

Measure the dependency directly from the caller's side:

```sh
time curl -s -o /dev/null -w '%{http_code} %{time_total}\n' payments:8080/health
```

Check the configured timeouts on the path, in code and config:

```sh
git grep -n -i -E 'timeout|deadline' -- '*.py' '*.yaml' '*.env'
```

Look for clients created without any timeout. Many HTTP libraries wait forever by default.

## How to get it working again

- **Shorten the timeout** on the call to the struggling dependency, so workers are freed quickly and callers fail fast.
- **Disable or degrade the feature** that depends on it, for example by showing cached data or hiding a widget.
- **Roll back** a change that removed or lengthened a timeout, or that added a slow call to a hot path.

Shortening timeouts can increase visible errors. It's still better than tying up every worker, which takes down endpoints that don't even use the slow dependency.

## How to fix it properly

- Set explicit connect and read timeouts on every client.
- Use deadlines that shrink as they go deeper: each inner call gets less time than its caller has left.
- Base timeouts on measured latency, comfortably above normal p99 but well below the caller's own limit.
- Combine timeouts with limited retries, backoff and circuit breakers.
- Alert on timeout rates per dependency.

## Common traps

- **No timeout at all**, often the library default.
- **Inner timeouts longer than outer ones**, so work continues after the user has given up.
- **Raising timeouts during an incident**, which ties up more workers for longer.
- **Retrying every timeout immediately**, which adds load at the worst moment.
