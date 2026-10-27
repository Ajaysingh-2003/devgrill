## What it is

An operation is idempotent if doing it twice has the same effect as doing it once. This matters because duplicates are normal in real systems. A queue may deliver a message more than once, a client retries after a timeout even though the first request succeeded, a worker crashes after doing the work but before acknowledging it. Most queues promise "at least once" delivery, never "exactly once".

When the operation isn't idempotent, a duplicate means real harm: a customer charged twice, two shipments, the same email sent three times, a counter incremented twice.

## How it shows up in an incident

- Customers report duplicate charges, orders or emails.
- Duplicates cluster around a deploy, a worker restart, a network blip or a timeout spike.
- Database rows that should be unique appear twice with near-identical timestamps.
- Retry counters or redelivery counts rise just before the duplicates.

## How to confirm it

Look for duplicate effects in the database:

```sql
select order_id, count(*), min(created_at), max(created_at)
from payments
group by order_id
having count(*) > 1
order by max(created_at) desc
limit 20;
```

Then trace one duplicate through the logs. Did the same message ID arrive twice, or did the client send two requests?

```sh
grep 'order_id=8812' worker.log api.log
```

Check whether workers were restarted or timed out around that time, and whether acknowledgements happen before or after the work is done.

## How to get it working again

- **Stop the source of repeats**: pause the consumer that redelivers, or fix the retry setting that resends successful work.
- **Deduplicate on the way in**: drop messages whose ID you have already processed, using a quick lookup table or Redis set.
- **Reconcile the damage**: refund duplicate charges and cancel duplicate orders, keeping a careful record.

Refunding or deleting without a clear list of what was duplicated can make a bad situation worse. Build the list first.

## How to fix it properly

- Give every operation an idempotency key: a client-generated ID for requests, a message ID for queue work.
- Store the key with the result in the same transaction as the side effect, and enforce it with a unique constraint.
- On a repeat, return the stored result instead of redoing the work.
- Acknowledge messages only after the work is committed.
- For external side effects like payments, pass the idempotency key to the provider, which most payment APIs support.
- Test it: send the same request or message twice and assert one effect.

## Common traps

- **Assuming exactly-once delivery** from a queue or a retrying client.
- **Checking "have I done this?" and then doing it** in two separate steps, which races under concurrency.
- **Acknowledging a message before the work commits**, so a crash loses it, or after an external call that can't be undone.
- **Deduplicating only in memory**, which forgets everything on restart.
