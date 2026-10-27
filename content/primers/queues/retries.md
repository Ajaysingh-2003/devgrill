## What it is

Retrying a failed operation is the simplest way to survive brief failures: a dropped connection, a dependency restarting, a lock that clears a moment later. Done well, retries hide transient errors from users. Done badly, they turn a small problem into a big one.

The danger is that retries add load exactly when a system is struggling. If a dependency slows down and every caller retries three times immediately, it receives four times the traffic at its weakest moment. Retries at several layers multiply: three retries in the client, three in the API and three in the worker can mean 64 calls for one user action.

## How it shows up in an incident

- Request volume to a dependency jumps while user traffic is flat.
- Error rates stay high after the original cause is fixed, because the retry backlog keeps the dependency busy.
- Logs show the same request ID many times in quick succession.
- Queues fill with retried messages, pushing back fresh work.
- Duplicate side effects appear if the retried operation wasn't idempotent.

## How to confirm it

Compare incoming user traffic with traffic to the struggling dependency. If the dependency sees far more calls, retries are amplifying:

```sh
grep 'request_id=' api.log | grep -o 'request_id=[a-z0-9-]*' | sort | uniq -c | sort -rn | head
```

Check the retry settings in the code and in every client library on the path: HTTP clients, database drivers, queue consumers and service meshes often retry by default.

```sh
git grep -n -i 'retry\|max_retries\|backoff' -- '*.py' '*.yaml' '*.env'
```

## How to get it working again

- **Lower or switch off retries** on the path that is amplifying load, often through config or a feature flag.
- **Shed load** at the edge so the struggling dependency can recover.
- **Drain the retry backlog slowly**, or park it and replay it once the dependency is healthy.
- **Roll back** a recent change that added retries or shortened timeouts.

Turning retries off entirely can surface every transient error to users. It is a short-term lever while the dependency recovers.

## How to fix it properly

- Use exponential backoff with jitter, so retries spread out instead of arriving in waves.
- Cap the number of retries, and retry at one layer only.
- Retry only errors that are likely to be transient, such as timeouts and 503s, never validation errors or 4xx responses.
- Add a retry budget: if more than a small share of recent calls are retries, stop retrying.
- Combine with circuit breakers and timeouts, and make retried operations idempotent.

## Common traps

- **Immediate retries with no backoff**, which hit a struggling service in lockstep.
- **Retrying at every layer**, which multiplies the calls.
- **Retrying non-idempotent operations** like payments without an idempotency key.
- **Treating every error as retryable**, including bad input that will never succeed.
