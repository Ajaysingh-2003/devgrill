"""ShopKart orders worker: takes pending orders from the Valkey queue, charges them, marks
them paid. Logs JSON like the API. Exposes Prometheus metrics on :9100."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from typing import Any

import psycopg
import redis
from prometheus_client import Counter, Gauge, start_http_server

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://shopkart:shopkart@postgres:5432/shopkart"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUE = "orders:pending"
#: Attempts before an order is parked in the dead-letter list (0 = retry forever).
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))
POLL_S = float(os.environ.get("POLL_S", "1"))

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


def charge(order: dict[str, Any]) -> None:
    """A pretend payment call. Scenarios can make this slow or flaky."""
    if order.get("quantity", 1) <= 0:
        raise ValueError("quantity must be positive")
    time.sleep(0.02)


def process(conn: psycopg.Connection[Any], queue: redis.Redis, raw: bytes) -> None:
    order = json.loads(raw)
    attempt = order.get("attempt", 0) + 1
    try:
        charge(order)
        with conn.transaction():
            conn.execute(
                "UPDATE orders SET status = 'paid', updated_at = now() WHERE id = %s",
                (order["id"],),
            )
        PROCESSED.labels("paid").inc()
        log.info("order paid", extra={"x_order_id": order["id"], "x_attempt": attempt})
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
            queue.lpush(QUEUE, json.dumps(order))
            PROCESSED.labels("retried").inc()
            log.warning(
                "order retried",
                extra={"x_order_id": order["id"], "x_attempt": attempt, "x_error": str(exc)},
            )


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    start_http_server(9100)
    queue = redis.Redis.from_url(REDIS_URL, socket_timeout=5)
    log.info("started", extra={"x_queue": QUEUE, "x_max_attempts": MAX_ATTEMPTS})
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
                    process(conn, queue, raw)
        except (psycopg.OperationalError, redis.RedisError) as exc:
            log.error("backend unavailable, retrying", extra={"x_error": type(exc).__name__})
            time.sleep(2)


if __name__ == "__main__":
    main()
