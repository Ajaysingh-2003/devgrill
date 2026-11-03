"""Invariant: order pages that can be a little behind are still served by the replica.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN (read-only, primary).
Picks 50 old orders of shoppers who haven't ordered in the last five minutes, opens their
order pages, and counts how many of those reads reached the replica (from the replica's own
statistics). Prints {"replica_share": share of the 50}.
"""

import json
import os
import time

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
REPLICA_DSN = PG_DSN.replace("@postgres-db:", "@postgres-replica:")
# A busy backend may hold its statistics up to 10 s before reporting them.
STATS_SETTLE_S = 11
READS = (
    "SELECT coalesce(sum(coalesce(idx_scan, 0) + seq_scan), 0)"
    " FROM pg_catalog.pg_stat_user_tables WHERE relname = 'orders'"
)


def replica_reads() -> int:
    # A fresh connection each time: closing it flushes its own statistics first.
    with psycopg.connect(REPLICA_DSN, autocommit=True, connect_timeout=5) as conn:
        return int(conn.execute(READS).fetchone()[0])


with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    orders = conn.execute(
        "SELECT id, user_id FROM public.orders o WHERE created_at < now() - interval '10 minutes'"
        " AND NOT EXISTS (SELECT 1 FROM public.orders r WHERE r.user_id = o.user_id"
        "   AND r.created_at > now() - interval '5 minutes')"
        " ORDER BY random() LIMIT 50"
    ).fetchall()

time.sleep(STATS_SETTLE_S)
before = replica_reads()
with httpx.Client(base_url=TARGET, timeout=10) as client:
    for order_id, user_id in orders:
        client.get(f"/users/{user_id}/orders/{order_id}")
time.sleep(STATS_SETTLE_S)
after = replica_reads()
print(json.dumps({"replica_share": round((after - before) / max(1, len(orders)), 2)}))
