## What it is

A double spend is a race condition with money attached: the same balance, voucher, credit or inventory is used twice. A wallet with ₹500 pays for two ₹400 orders. A single-use coupon is redeemed by three orders. A refund is issued twice. Each request checked the balance, saw enough, and went ahead, because none of them saw the others in time.

It usually comes from a read, check, write pattern on a balance, from retries without idempotency, or from processing the same event twice: a payment webhook delivered more than once, a queue message redelivered, a user double-clicking "Pay".

## How it shows up in an incident

- Balances go negative, or the sum of transactions doesn't match the stored balance.
- Finance or support reports duplicate refunds, payouts or coupon uses.
- Problems cluster around retries, webhook redeliveries, timeouts or traffic spikes.
- Two ledger entries for the same order or payment ID, seconds apart.

## How to confirm it

Reconcile balances against the ledger:

```sql
select a.id, a.balance, coalesce(sum(t.amount), 0) as ledger_total
from accounts a
left join transactions t on t.account_id = a.id
group by a.id, a.balance
having a.balance <> coalesce(sum(t.amount), 0);
```

Look for the same external reference used twice:

```sql
select payment_ref, count(*), array_agg(id)
from transactions
group by payment_ref
having count(*) > 1;
```

Then trace one duplicate through the logs to see whether two requests, two webhooks or two queue deliveries caused it.

## How to get it working again

- **Freeze the affected operation**: pause payouts, refunds or redemptions while you investigate.
- **Stop the duplicate source**: disable the webhook retry, the consumer or the client path that resends.
- **Build a list of affected accounts and transactions** before reversing anything, and get it checked by someone else.

Reversing money movements is itself risky. Every correction should be a new ledger entry with a reason, never an edit or deletion of history.

## How to fix it properly

- Use an append-only ledger: every change is a new row, and the balance is derived from or checked against it.
- Enforce rules in the database: `check (balance >= 0)`, and a unique constraint on the external reference (payment ID, webhook ID, idempotency key).
- Update balances atomically: `update accounts set balance = balance - $2 where id = $1 and balance >= $2`, and fail if no row changed.
- Make every money operation idempotent, keyed by a reference the caller sends.
- Reconcile automatically every day, and alert on any mismatch.

## Common traps

- **Checking the balance in application code** and writing it in a separate statement.
- **Trusting webhooks to arrive exactly once**: providers retry, and so do networks.
- **Fixing by editing balances** instead of adding correcting ledger entries.
- **Relying on the UI** to prevent double submits, when retries and APIs bypass it.
