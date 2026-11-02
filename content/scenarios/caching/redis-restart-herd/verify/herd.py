"""Invariant: an empty cache costs one build of the deals page, not one per shopper.

Runs in the verifier's probe container with TARGET (the API), PG_DSN (read-only) and CACHE_HOST
(Valkey). Empties the cache as a restart does, then sends 30 shoppers to /deals at once. Counts
the pages that failed or listed the wrong products (the truth is the database), and how many
times Postgres read the whole reviews table meanwhile: every build of the page reads it once.
Prints {"builds": n, "failed": n, "wrong": n}.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import psycopg
import redis

TARGET = os.environ["TARGET"]
PG_DSN = os.environ["PG_DSN"]
SHOPPERS = 30
STATS_SETTLE_S = 1.5

# The landing page's definition: the best-rated products in stock in each category, three per
# category, among products with at least five reviews.
EXPECTED = """
WITH rated AS (
  SELECT product_id, round(avg(rating), 2) AS rating_avg, count(*) AS rating_count
  FROM public.reviews GROUP BY product_id HAVING count(*) >= 5),
ranked AS (
  SELECT p.id, p.category, row_number() OVER (PARTITION BY p.category
    ORDER BY r.rating_avg DESC, r.rating_count DESC, p.id) AS rank
  FROM public.products p JOIN rated r ON r.product_id = p.id WHERE p.stock > 0)
SELECT id FROM ranked WHERE rank <= 3 ORDER BY category, rank
"""
SEQ_READ = (
    "SELECT seq_tup_read, greatest(n_live_tup, 1) FROM pg_catalog.pg_stat_user_tables"
    " WHERE relname = 'reviews'"
)


def visit(client: httpx.Client) -> list[int] | None:
    try:
        res = client.get("/deals")
        if res.status_code != 200:
            return None
        return [item.get("id") for item in res.json().get("items", [])]
    except httpx.HTTPError, ValueError, AttributeError:
        return None


# The truth, on a connection of its own: closing it flushes its statistics, so its own read
# of the reviews table can't land in the count below.
with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    conn.execute("SET search_path = pg_catalog, public")
    expected = [row[0] for row in conn.execute(EXPECTED).fetchall()]
time.sleep(STATS_SETTLE_S)

with psycopg.connect(PG_DSN, autocommit=True, connect_timeout=5) as conn:
    conn.execute("SET search_path = pg_catalog, public")
    before, rows = conn.execute(SEQ_READ).fetchone()
    redis.Redis(host=os.environ["CACHE_HOST"], port=6379, socket_timeout=5).flushall()
    with (
        httpx.Client(base_url=TARGET, timeout=10) as client,
        ThreadPoolExecutor(SHOPPERS) as pool,
    ):
        pages = list(pool.map(lambda _: visit(client), range(SHOPPERS)))
    time.sleep(STATS_SETTLE_S)
    after, _ = conn.execute(SEQ_READ).fetchone()

failed = sum(page is None for page in pages)
wrong = sum(page is not None and page != expected for page in pages)
print(json.dumps({"builds": round((after - before) / rows, 1), "failed": failed, "wrong": wrong}))
