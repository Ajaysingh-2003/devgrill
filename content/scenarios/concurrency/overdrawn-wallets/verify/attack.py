"""Invariant: two payments at once can't both spend the same money.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN (read-only). For 20
wallets: top up, then fire two card payments at the same moment, each for 70% of the
balance. At most one may go through. Prints {"double_spends": wallets where both did,
"overdrawn": of those wallets, how many ended below zero}.
"""

import json
import os
import random
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
double_spends = overdrawn = 0

with (
    httpx.Client(base_url=TARGET, timeout=10) as client,
    psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn,
    ThreadPoolExecutor(2) as pool,
):
    for wallet in random.sample(range(1, 1001), 20):
        # A wallet the incident left overdrawn is topped up past zero first: only overdrafts
        # made here count.
        row = conn.execute(
            "SELECT balance_cents FROM public.accounts WHERE id = %s", (wallet,)
        ).fetchone()
        top_up = max(50000, 50000 - int(row[0]))
        client.post(
            "/transfers", json={"from_account": 0, "to_account": wallet, "amount_cents": top_up}
        )
        row = conn.execute(
            "SELECT balance_cents FROM public.accounts WHERE id = %s", (wallet,)
        ).fetchone()
        amount = int(row[0] * 0.7)
        body = {"account_id": wallet, "merchant_id": 9001 + wallet % 20, "amount_cents": amount}
        results = list(
            pool.map(lambda b: client.post("/payments", json=b).status_code, [body, body])
        )
        if results.count(201) == 2:
            double_spends += 1
        row = conn.execute(
            "SELECT balance_cents FROM public.accounts WHERE id = %s", (wallet,)
        ).fetchone()
        overdrawn += row[0] < 0

print(json.dumps({"double_spends": double_spends, "overdrawn": overdrawn}))
