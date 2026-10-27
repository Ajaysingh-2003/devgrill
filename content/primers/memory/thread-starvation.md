## What it is

A web server handles requests with a fixed number of workers: processes, threads, or event loops. Thread starvation happens when all of them are busy, usually waiting, and new requests queue with nothing to serve them. The CPU can be nearly idle while the service is effectively down.

In Python this takes a few forms. In a threaded or process-based server, every worker is blocked on a slow call: an external API with no timeout, a database lock, a large upload. In an async server, one piece of blocking code, a synchronous HTTP call, `time.sleep`, a heavy CPU loop, freezes the event loop, so every request on that worker waits.

## How it shows up in an incident

- Latency rises sharply for all endpoints at once, even simple ones like a health check.
- Request queue length or "requests in flight" sits at the worker limit.
- CPU is low, because workers are waiting rather than working.
- Health checks start failing, and the orchestrator restarts healthy-but-busy containers, making it worse.
- It often follows a slowdown in one dependency, which ties up workers for every endpoint.

## How to confirm it

See what the workers are doing right now. `py-spy` shows the stack of every thread without stopping the process:

```sh
py-spy dump --pid 1234
```

If most threads are in the same place, a socket read, a database call, `time.sleep`, that's the bottleneck. Check how long a simple endpoint takes compared with normal:

```sh
time curl -s api:8000/healthz
```

Look for outbound calls without timeouts, or blocking calls inside async code:

```sh
git grep -n -E 'requests\.(get|post)\(|time\.sleep\(' -- '*.py'
```

## How to get it working again

- **Cut off the slow dependency**: disable the feature that calls it, or fail fast with a short timeout through config.
- **Add workers or replicas** temporarily, if the dependency can take more load.
- **Restart stuck workers** to clear requests that will never finish.
- **Roll back** a deploy that introduced a blocking call or removed a timeout.

More workers only help if the thing they wait on can serve them. If they all wait on one saturated dependency, more workers make it worse.

## How to fix it properly

- Put a timeout on every network call, and fail fast instead of waiting forever.
- Keep blocking code out of async handlers: use async clients, or run blocking work in a thread pool.
- Isolate slow or optional dependencies with separate worker pools, so they can't take every worker.
- Use circuit breakers so calls to a failing dependency stop quickly.
- Monitor in-flight requests and queue wait time, not just CPU.

## Common traps

- **Looking at CPU and concluding the service is fine**: starved workers wait, they don't compute.
- **Calling a synchronous HTTP library from async code**, which blocks the whole event loop.
- **Letting health checks share the same workers** and get killed during a slowdown.
- **No timeouts on outbound calls**, so one slow partner takes the whole service down.
