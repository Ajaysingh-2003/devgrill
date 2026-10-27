## What it is

Consumer lag is how far behind the workers are: the number of messages waiting, or the age of the oldest unprocessed message. A queue absorbs bursts, so some lag is normal. Lag becomes an incident when producers add work faster than consumers finish it for long enough that the backlog keeps growing, and the delay becomes visible to users.

Lag grows for two reasons: more work arrives (a traffic spike, a batch import, a retry storm), or each message takes longer to process (a slow dependency, a lock, a bad deploy). Often it is the second, even when it looks like the first.

## How it shows up in an incident

- Queue depth climbs steadily and the age of the oldest message keeps rising.
- Users report delays: emails arrive late, payments show as pending, exports never finish.
- Worker CPU may be low if workers are waiting on a slow database or API.
- Processing time per message is higher than usual in worker logs or metrics.
- If messages expire or have deadlines, they start to time out unprocessed.

## How to confirm it

Measure depth and age, and take two readings a minute apart to see the trend:

```sh
redis-cli -h redis LLEN jobs
redis-cli -h redis XINFO GROUPS jobs
redis-cli -h redis XPENDING jobs workers
```

Compare how fast messages arrive with how fast they are finished. If you log processing time, check whether it changed:

```sh
grep 'processed' worker.log | tail -200 | grep -o 'took_ms=[0-9]*' | sort -t= -k2 -n | tail
```

Check what workers are waiting on: database locks, slow queries, or an external API timing out.

## How to get it working again

- **Fix what made processing slow first**, for example by rolling back a deploy or failing over a slow dependency.
- **Add consumers** if the work is truly parallel and the dependencies have headroom.
- **Pause non-urgent producers** such as batch imports, so urgent work gets through.
- **Prioritise**: move urgent messages to a separate queue or let workers take them first.

Adding consumers when they are all waiting on the same database adds more pressure to that database and can make lag worse.

## How to fix it properly

- Alert on the age of the oldest message, not just depth. Age tells you about user impact.
- Separate queues by priority, so a bulk job can't delay password resets.
- Autoscale consumers on lag, within limits that protect shared dependencies.
- Set timeouts on everything a worker calls, so one slow dependency can't stall every worker.
- Load-test the consumer path with realistic message volumes and payloads.

## Common traps

- **Scaling workers into a bottlenecked database**, which turns lag into an outage.
- **Watching only queue depth** when a few huge messages, or a bad deploy, change the processing time.
- **Mixing urgent and bulk work** in one queue.
- **Letting retries add to the backlog** without backoff or a retry limit.
