## What it is

A poison message is a message that a consumer can never process successfully. Maybe its payload is malformed, refers to data that no longer exists, or triggers a bug. The worker picks it up, fails, and the queue hands it out again. If nothing stops the cycle, that one message is retried forever.

The damage depends on the queue. With strict ordering, or a single consumer, one poison message blocks everything behind it. With many consumers, it wastes capacity and floods the logs while the rest of the queue slowly backs up.

## How it shows up in an incident

- Queue depth grows steadily while workers look busy.
- The same error repeats in worker logs, often with the same message ID or payload.
- Worker processes crash and restart in a loop, or their retry counters climb.
- Downstream effects stop: emails aren't sent, orders aren't fulfilled, reports aren't generated.
- Throughput drops to near zero even though workers are running.

## How to confirm it

Look for repeated failures of the same message in the worker logs:

```sh
grep -i error worker.log | tail -50
grep -o 'message_id=[a-z0-9-]*' worker.log | sort | uniq -c | sort -rn | head
```

Check the queue's depth and its oldest message. For a Redis list or stream:

```sh
redis-cli -h redis LLEN jobs
redis-cli -h redis LRANGE jobs 0 0
redis-cli -h redis XPENDING jobs workers
```

In a Redis stream, `XPENDING` shows messages delivered but never acknowledged, with how many times each was delivered. A message delivered dozens of times is your suspect.

## How to get it working again

- **Move the bad message aside**: put it in a dead-letter queue or a holding list, so the rest of the queue can drain.
- **Roll back** a recent change if the poison messages started with a deploy that changed the payload format or the consumer.
- **Add workers** only after the blocker is removed, to clear the backlog faster.

Deleting a message gets the queue moving, but loses the work. Prefer parking it somewhere you can inspect and replay it later.

## How to fix it properly

- Cap retries: after a few failures, move the message to a dead-letter queue automatically.
- Retry with backoff, so a temporary failure doesn't hammer a dependency.
- Validate messages when they are produced, not only when they are consumed.
- Version message formats, and make consumers tolerate the old and new versions during a deploy.
- Alert on dead-letter queue size, on queue age, and on repeated failures of the same message.
- Make it easy to inspect and replay dead-lettered messages once the bug is fixed.

## Common traps

- **Restarting workers**, which just picks up the same poison message again.
- **Scaling consumers** while one message blocks an ordered queue.
- **Infinite retries with no backoff**, which turn one bad message into load on every dependency.
- **Silently dropping failures**, which hides lost work until a customer notices.
