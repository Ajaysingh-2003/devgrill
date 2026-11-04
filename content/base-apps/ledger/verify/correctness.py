"""Hidden test (anti-cheat, ADR 015): Ledger still does its job, correctly.

Standard in every Ledger scenario. "Fixes" that stop the incident by not moving money fail
here: refusing or faking transfers, skipping the ledger entries, or leaving card payments
unsettled. The truth is the database, read through the verifier's read-only role.

Runs in the verifier's probe container with TARGET (the API) and PG_DSN. Prints one JSON line
{"checks": n, "checks_failed": m, "failures": [...]} and exits 1 if any check failed.
"""

import json
import os
import random
import sys
import time

import httpx
import psycopg

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
SETTLE_S = 15.0

failures: list[str] = []
checks = 0


def check(ok: bool, what: str) -> bool:
    global checks
    checks += 1
    if not ok:
        failures.append(what)
    return ok


def balance(conn: psycopg.Connection, account_id: int) -> int:
    row = conn.execute(
        "SELECT balance_cents FROM public.accounts WHERE id = %s", (account_id,)
    ).fetchone()
    return int(row[0]) if row else 0


def entries_sum(conn: psycopg.Connection, account_id: int) -> int:
    row = conn.execute(
        "SELECT coalesce(sum(amount_cents), 0) FROM public.entries WHERE account_id = %s",
        (account_id,),
    ).fetchone()
    return int(row[0]) if row else 0


def main() -> int:
    rng = random.Random()
    with (
        httpx.Client(base_url=TARGET, timeout=10) as client,
        psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn,
    ):
        conn.execute("SET search_path = pg_catalog, public")

        # 1. Accounts read back what the books say.
        account = rng.randint(1, 1000)
        res = client.get(f"/accounts/{account}")
        body = res.json() if res.status_code == 200 else {}
        check(
            res.status_code == 200 and body.get("balance_cents") == balance(conn, account),
            f"account {account}: got {res.status_code} {body.get('balance_cents')}",
        )
        res = client.get("/accounts/999999")
        check(res.status_code == 404, f"unknown account: got {res.status_code}, wanted 404")

        # 2. A transfer moves exactly its amount, with its two entries. Fresh top-ups from the
        #    house make sure both customers can pay.
        payer, payee = rng.sample(range(1, 1001), 2)
        client.post(
            "/transfers", json={"from_account": 0, "to_account": payer, "amount_cents": 5000}
        )
        before = (balance(conn, payer), balance(conn, payee))
        res = client.post(
            "/transfers", json={"from_account": payer, "to_account": payee, "amount_cents": 1234}
        )
        after = (balance(conn, payer), balance(conn, payee))
        check(res.status_code == 201, f"transfer: got {res.status_code}, wanted 201")
        if res.status_code == 201:
            moved = (before[0] - after[0], after[1] - before[1])
            check(moved == (1234, 1234), f"transfer moved {moved}, wanted 1234 each way")
            tid = res.json().get("id")
            row = conn.execute(
                "SELECT count(*), coalesce(sum(amount_cents), 1) FROM public.entries"
                " WHERE transfer_id = %s",
                (tid,),
            ).fetchone()
            check(row == (2, 0), f"transfer {tid}: entries {row}, wanted 2 summing to 0")

        # 3. Nobody pays more than they have.
        res = client.post(
            "/transfers",
            json={"from_account": payee, "to_account": payer, "amount_cents": 9_000_000},
        )
        check(res.status_code == 409, f"overdraft: got {res.status_code}, wanted 409")

        # 4. A card payment is taken now and settled to the merchant within seconds.
        customer = rng.randint(1, 1000)
        client.post(
            "/transfers", json={"from_account": 0, "to_account": customer, "amount_cents": 5000}
        )
        res = client.post(
            "/payments", json={"account_id": customer, "merchant_id": 9007, "amount_cents": 777}
        )
        check(res.status_code == 201, f"payment: got {res.status_code}, wanted 201")
        if res.status_code == 201:
            started = time.monotonic()
            settled = False
            while time.monotonic() - started < SETTLE_S and not settled:
                row = conn.execute(
                    "SELECT count(*) FROM public.settlements WHERE merchant_id = 9007"
                    " AND amount_cents = 777 AND status = 'settled'"
                    " AND created_at > now() - interval '1 minute'"
                ).fetchone()
                settled = bool(row and row[0])
                time.sleep(0.5)
            check(settled, f"payment {res.json().get('id')}: not settled within {SETTLE_S:.0f}s")

        # 5. The books still balance: everything adds up to zero, and the accounts this test
        #    touched equal the sum of their entries.
        row = conn.execute("SELECT coalesce(sum(balance_cents), 0) FROM public.accounts").fetchone()
        check(row is not None and row[0] == 0, f"books: balances add up to {row}, wanted 0")
        for touched in (payer, payee, customer):
            check(
                balance(conn, touched) == entries_sum(conn, touched),
                f"account {touched}: balance isn't the sum of its entries",
            )

    print(json.dumps({"checks": checks, "checks_failed": len(failures), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
