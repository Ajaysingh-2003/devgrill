"""ShopKart orders worker: takes pending orders from the Valkey queue, charges them through the
payment provider, marks them paid. Logs JSON like the API. Exposes Prometheus metrics on :9100.

Orders are charged in the order they were placed: a failed order is retried at the head of
the queue, before the ones behind it. An order that fails on its own (it can't be charged)
uses up an attempt, and MAX_ATTEMPTS sends it to the dead-letter list (orders:dead). When the
provider is the problem (no answer in time, unreachable, or "come back later"), the order is
fine: it is retried without using up an attempt. Tunables live in config/worker.env, deployed
with the code."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import psycopg
import redis
from prometheus_client import Counter, Gauge, start_http_server


def _load_env_file(path: Path) -> None:
    """config/worker.env: KEY=value lines; the process environment wins."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip())


_load_env_file(Path(__file__).resolve().parent / "config" / "worker.env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://shopkart:shopkart@postgres:5432/shopkart"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://payment-gateway:8080")
QUEUE = "orders:pending"
#: Attempts before an order is parked in the dead-letter list (0 = retry forever).
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))
POLL_S = float(os.environ.get("POLL_S", "1"))
#: Pause before a failed order is tried again (it keeps its place at the head).
RETRY_BACKOFF_S = float(os.environ.get("RETRY_BACKOFF_S", "0.2"))
#: How long to wait for the payment provider to answer a charge (seconds).
PAYMENT_TIMEOUT_S = float(os.environ.get("PAYMENT_TIMEOUT_S", "10"))
#: Orders charged at once (threads, each taking the next order from the queue).
CONSUMERS = int(os.environ.get("CONSUMERS", "1"))

PROCESSED = Counter("orders_processed_total", "Orders processed", ["result"])
QUEUE_DEPTH = Gauge("orders_queue_depth", "Pending orders in the queue")
LAG = Gauge("orders_consumer_lag_seconds", "Age of the oldest pending order")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": "worker",
            "msg": record.getMessage(),
        }
        entry.update({k[2:]: v for k, v in record.__dict__.items() if k.startswith("x_")})
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, separators=(",", ":"))


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
log = logging.getLogger("worker")

running = True


def stop(*_: Any) -> None:
    global running
    running = False


class ProviderUnavailable(Exception):
    """The provider didn't charge the order this time (no answer in time, unreachable, busy):
    nothing is wrong with the order, so try again."""


def charge(conn: psycopg.Connection[Any], payments: httpx.Client, order: dict[str, Any]) -> None:
    """Charges the order through the payment provider (the provider emails the receipt)."""
    if order.get("quantity", 1) <= 0:
        raise ValueError("quantity must be positive")
    row = conn.execute("SELECT total_cents FROM orders WHERE id = %s", (order["id"],)).fetchone()
    amount = row[0] if row else 0
    try:
        res = payments.post("/charges", json={"order_id": order["id"], "amount_cents": amount})
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(type(exc).__name__) from exc
    if res.status_code in (409, 429) or res.status_code >= 500:
        raise ProviderUnavailable(f"provider answered {res.status_code}")
    if res.status_code >= 400:
        raise ValueError(f"declined: {res.text[:120]}")


def process(
    conn: psycopg.Connection[Any], queue: redis.Redis, payments: httpx.Client, raw: bytes
) -> None:
    order = json.loads(raw)
    attempt = order.get("attempt", 0) + 1
    try:
        charge(conn, payments, order)
        with conn.transaction():
            conn.execute(
                "UPDATE orders SET status = 'paid', updated_at = now() WHERE id = %s",
                (order["id"],),
            )
        PROCESSED.labels("paid").inc()
        log.info("order paid", extra={"x_order_id": order["id"], "x_attempt": attempt})
    except ProviderUnavailable as exc:
        # Back at the head, attempt unchanged: the provider failed, not the order.
        queue.rpush(QUEUE, raw)
        PROCESSED.labels("retried").inc()
        log.warning(
            "payment provider unavailable, retrying",
            extra={"x_order_id": order["id"], "x_error": str(exc)},
        )
        time.sleep(RETRY_BACKOFF_S)
    except Exception as exc:
        order["attempt"] = attempt
        if MAX_ATTEMPTS and attempt >= MAX_ATTEMPTS:
            queue.rpush("orders:dead", json.dumps(order))
            with conn.transaction():
                conn.execute(
                    "UPDATE orders SET status = 'failed', updated_at = now() WHERE id = %s",
                    (order["id"],),
                )
            PROCESSED.labels("dead").inc()
            log.error(
                "order moved to dead letter", extra={"x_order_id": order["id"], "x_error": str(exc)}
            )
        else:
            # Back at the head: orders are charged in the order they were placed.
            queue.rpush(QUEUE, json.dumps(order))
            PROCESSED.labels("retried").inc()
            log.warning(
                "order retried",
                extra={"x_order_id": order["id"], "x_attempt": attempt, "x_error": str(exc)},
            )
            time.sleep(RETRY_BACKOFF_S)


def consume() -> None:
    """One consumer: its own connections, taking the next order until the worker stops."""
    queue = redis.Redis.from_url(REDIS_URL, socket_timeout=5)
    payments = httpx.Client(base_url=PAYMENTS_URL, timeout=PAYMENT_TIMEOUT_S)
    while running:
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                while running:
                    QUEUE_DEPTH.set(queue.llen(QUEUE))
                    item = queue.brpop([QUEUE], timeout=int(POLL_S) or 1)
                    if item is None:
                        LAG.set(0)
                        continue
                    _, raw = item
                    order = json.loads(raw)
                    LAG.set(max(0.0, time.time() - float(order.get("enqueued_at", time.time()))))
                    process(conn, queue, payments, raw)
        except (psycopg.OperationalError, redis.RedisError) as exc:
            log.error("backend unavailable, retrying", extra={"x_error": type(exc).__name__})
            time.sleep(2)


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    start_http_server(9100)
    log.info(
        "started",
        extra={"x_queue": QUEUE, "x_max_attempts": MAX_ATTEMPTS, "x_consumers": CONSUMERS},
    )
    threads = [threading.Thread(target=consume, daemon=True) for _ in range(CONSUMERS)]
    for thread in threads:
        thread.start()
    while running:
        time.sleep(0.5)


if __name__ == "__main__":
    main()
