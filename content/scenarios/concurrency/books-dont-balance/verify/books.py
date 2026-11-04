"""Invariant: the books balance.

Runs in the verifier's probe container with PG_DSN (read-only). In one snapshot: how many
accounts have a balance that isn't the sum of their entries, and how far all balances are from
adding up to zero. Prints {"accounts_off": n, "books_off_cents": n}.
"""

import json
import os

import psycopg

PG_DSN = os.environ["PG_DSN"]
SQL = """
SELECT
  (SELECT count(*) FROM public.accounts a
     LEFT JOIN (SELECT account_id, sum(amount_cents) AS total FROM public.entries
                GROUP BY account_id) e ON e.account_id = a.id
    WHERE a.balance_cents <> coalesce(e.total, 0)),
  (SELECT abs(coalesce(sum(balance_cents), 0)) FROM public.accounts)
"""

with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    off, books = conn.execute(SQL).fetchone()
print(json.dumps({"accounts_off": int(off), "books_off_cents": int(books)}))
