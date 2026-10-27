## What it is

A retry storm is what happens when many clients retry at once against a service that is already struggling. A dependency slows down for a moment. Its callers time out and retry. Their callers time out and retry too. The struggling service now receives several times its normal traffic, which keeps it from recovering. The original problem may be long gone, but the retries keep the system overloaded. This is a self-sustaining failure, sometimes called a metastable failure.

Storms are amplified by retries at several layers, immediate retries without backoff, short timeouts, and clients that all retry on the same schedule.

## How it shows up in an incident

- Traffic to a dependency far higher than user traffic would explain.
- The system stays down after the trigger is fixed, and only recovers when load is cut.
- Waves of requests at regular intervals, matching the retry delay.
- Error rates and latency climbing together across many services that share the dependency.
- Queues filling with retried work and connection pools full everywhere.

## How to confirm it

Compare user-facing request rates with the rate of calls to the struggling service. A big multiplier means retries:

```sh
grep -c 'GET /products' gateway.log
grep -c 'retrying' api.log
```

Look for the same request ID retried many times:

```sh
grep -o 'request_id=[a-z0-9-]*' api.log | sort | uniq -c | sort -rn | head
```

Check every layer for retry settings: HTTP clients, SDKs, service mesh, load balancer and queue consumers can all retry independently.

## How to get it working again

- **Shed load hard** at the edge: return 503 to a share of requests, or turn off non-essential traffic, so the dependency can recover.
- **Turn retries down or off** at the layers you control, through config or a flag.
- **Let it drain**, then restore traffic gradually rather than all at once.
- **Restart only after load is reduced**: restarting into the same storm just repeats it.

Cutting load means some users see errors for a while. That is the price of getting out of the loop, and it is much shorter than staying in it.

## How to fix it properly

- Exponential backoff with jitter on every retry, so retries spread out over time.
- Retry at one layer only, with a small cap on retries.
- Retry budgets: when retries exceed a small share of traffic, stop retrying.
- Circuit breakers that stop calling a failing dependency for a while.
- Load shedding and admission control, so a service rejects excess work quickly instead of queueing it.
- Test overload and recovery, not just failure.

## Common traps

- **Restarting the overloaded service** while clients keep retrying, so it falls over again.
- **Fixing the original trigger and waiting**, when the retries alone now keep it down.
- **Adding capacity** that the retries immediately consume.
- **Synchronised retries** with a fixed delay, which hit the service in waves.
