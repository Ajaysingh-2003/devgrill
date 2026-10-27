## What it is

A race condition is a bug where the result depends on the timing of operations that run at the same time. Two requests read the same value, both decide based on it, and both write. One update silently overwrites the other, or both pass a check that only one should have passed.

The classic shape is read, then decide, then write: read the stock count, check it is above zero, then decrement. With two requests in parallel, both read 1, both pass the check, and both sell the last item. Races hide in normal testing because they need concurrency and unlucky timing, then appear under real load.

## How it shows up in an incident

- Data that should be impossible: negative stock, a counter lower than the number of events, two users holding the same seat.
- Problems that only appear under load or during traffic spikes, and can't be reproduced locally.
- Lost updates: a user changes a field and the change disappears.
- Bugs that cluster around retries, double-clicks or several workers processing related items.

## How to confirm it

Find the impossible data and look at the timing of the writes:

```sql
select id, stock, updated_at from products where stock < 0;
select product_id, count(*), min(created_at), max(created_at)
from order_items
where product_id = 1042 and created_at > now() - interval '1 hour'
group by product_id;
```

Read the code for the read, check, write pattern, especially where the read and the write happen in different statements or different transactions:

```sh
git grep -n -E 'select .* for update|\.get\(|if .* > 0' -- '*.py'
```

Reproduce it on purpose by sending the same request many times in parallel:

```sh
seq 20 | xargs -P 20 -I{} curl -s -X POST api:8000/orders -d '{"product_id":1042}'
```

## How to get it working again

- **Stop the bleeding**: disable the feature, limit the endpoint to one request at a time, or route the hot items through a single worker.
- **Repair the data** carefully, with a written list of what was wrong and what you changed.
- **Roll back** a change that introduced the race, such as removing a lock or splitting a transaction.

## How to fix it properly

- Make the database do the check and the write in one step: `update products set stock = stock - 1 where id = $1 and stock > 0`, then check how many rows changed.
- Use constraints: `check (stock >= 0)` and unique indexes turn a race into a clean error instead of bad data.
- Lock the rows you are about to change with `select ... for update` inside one transaction.
- Use optimistic concurrency: a version column, and fail the update if the version has moved.
- Write tests that run the same operation concurrently.

## Common traps

- **Adding a check in application code** that still reads and writes in separate steps.
- **Using a lock in process memory** when several app instances run at once.
- **Assuming low traffic means no races**: double-clicks and retries create concurrency on their own.
- **Fixing the data without fixing the code**, so it happens again under the next spike.
