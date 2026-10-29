"""Hidden test (anti-cheat, ADR 015): ShopKart still does its job, correctly.

Standard in every ShopKart scenario. Fast "fixes" that stop the incident by not doing the work
fail here: answering 503 or empty bodies, serving made-up or stale data, dropping writes,
404ing everything, or serving only the hot products. The truth is the database, read through
the verifier's read-only role.

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
HOT = [1042, 1043, 2210, 77, 9001]
CATALOGUE = 18402
SETTLE_S = 5.0

failures: list[str] = []
checks = 0


def check(ok: bool, what: str) -> bool:
    global checks
    checks += 1
    if not ok:
        failures.append(what)
    return ok


def truth(conn: psycopg.Connection, product_id: int) -> tuple[str, int] | None:
    row = conn.execute(
        "SELECT name, price_cents FROM public.products WHERE id = %s", (product_id,)
    ).fetchone()
    return (row[0], row[1]) if row else None


def ratings(conn: psycopg.Connection, product_id: int) -> tuple[float | None, int]:
    row = conn.execute(
        "SELECT round(avg(rating), 2)::float, count(*) FROM public.reviews WHERE product_id = %s",
        (product_id,),
    ).fetchone()
    return (row[0], row[1]) if row else (None, 0)


def eventually(fetch, expected, deadline_s: float = SETTLE_S):
    """Poll until fetch() == expected or the deadline passes; returns the last value seen."""
    started = time.monotonic()
    seen = fetch()
    while seen != expected and time.monotonic() - started < deadline_s:
        time.sleep(0.25)
        seen = fetch()
    return seen


def product(client: httpx.Client, product_id: int) -> tuple[int, dict]:
    res = client.get(f"/products/{product_id}")
    try:
        body = res.json()
    except ValueError:
        body = {}
    return res.status_code, body if isinstance(body, dict) else {}


def main() -> int:
    rng = random.Random()
    with (
        httpx.Client(base_url=TARGET, timeout=10) as client,
        psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn,
    ):
        conn.execute("SET search_path = pg_catalog, public")

        # 1. Products, hot and cold, match the database (name and price).
        sample = HOT[:2] + rng.sample(range(1, CATALOGUE + 1), 8)
        for pid in sample:
            expected = truth(conn, pid)
            status, body = product(client, pid)
            if status != 200 or (body.get("name"), body.get("price_cents")) != expected:
                # Allow a moment for a write in flight to land, once.
                time.sleep(1)
                expected = truth(conn, pid)
                status, body = product(client, pid)
            check(
                status == 200
                and body.get("id") == pid
                and (body.get("name"), body.get("price_cents")) == expected,
                f"product {pid}: got {status} {body.get('name')!r}/{body.get('price_cents')},"
                f" the database has {expected}",
            )

        # 1b. Their rating summaries are real (the expensive part can't just be skipped).
        for pid in sample[:4]:
            status, body = product(client, pid)
            expected_rating = ratings(conn, pid)
            check(
                status == 200
                and (body.get("rating_avg"), body.get("rating_count")) == expected_rating,
                f"ratings of product {pid}: got"
                f" {body.get('rating_avg')}/{body.get('rating_count')},"
                f" the reviews say {expected_rating}",
            )

        # 2. A product that doesn't exist is a 404, not a 200 or a 5xx.
        status, _ = product(client, CATALOGUE + 100_000)
        check(status == 404, f"unknown product: got {status}, wanted 404")

        # 3. Search still searches.
        res = client.get("/products", params={"q": "Trail", "limit": 5})
        items = res.json() if res.status_code == 200 else []
        check(
            res.status_code == 200
            and 0 < len(items) <= 5
            and all("trail" in str(i.get("name", "")).lower() for i in items),
            f"search: got {res.status_code} with"
            f" {len(items) if isinstance(items, list) else '?'} items",
        )

        # 4. Orders are written, at the right total.
        pid = rng.choice(HOT)
        res = client.post(
            "/orders", json={"user_id": rng.randint(1, 2000), "product_id": pid, "quantity": 2}
        )
        order = res.json() if res.status_code == 201 else {}
        row = (
            conn.execute(
                "SELECT o.total_cents, p.price_cents * 2 FROM public.orders o"
                " JOIN public.products p ON p.id = o.product_id WHERE o.id = %s",
                (order.get("id"),),
            ).fetchone()
            if order.get("id") is not None
            else None
        )
        check(
            res.status_code == 201 and row is not None and row[0] == row[1],
            f"order: got {res.status_code}, stored {row}",
        )

        # 5. A price change shows on the product page within seconds: a cold product, and a
        #    hot one (a hard-coded copy of the sale products can't keep up).
        cold = rng.randint(1, CATALOGUE)
        while cold in HOT:
            cold = rng.randint(1, CATALOGUE)
        for pid in (cold, rng.choice(HOT)):
            product(client, pid)  # cache it, if the app caches
            current = truth(conn, pid)
            new_price = (current[1] if current else 0) + rng.randint(1, 900)
            res = client.put(f"/products/{pid}/price", json={"price_cents": new_price})
            seen = eventually(lambda p=pid: product(client, p)[1].get("price_cents"), new_price)
            check(
                res.status_code == 200
                and seen == new_price
                and current is not None
                and truth(conn, pid) == (current[0], new_price),
                f"price change on product {pid}: wrote {new_price} ({res.status_code}),"
                f" page shows {seen}",
            )

    print(json.dumps({"checks": checks, "checks_failed": len(failures), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (httpx.HTTPError, psycopg.Error) as exc:
        print(
            json.dumps(
                {
                    "checks": checks,
                    "checks_failed": len(failures) + 1,
                    "failures": [*failures, f"error: {exc}"],
                }
            )
        )
        sys.exit(1)
