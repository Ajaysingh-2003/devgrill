"""Ledger worker: pays merchants out for card payments, and audits the books.

Settlement: each card payment leaves a pending settlement. Consumers take them in batches
(FOR UPDATE SKIP LOCKED, so two consumers never take the same one) and pay each one from the
house's clearing balance to the merchant: a transfer, two entries and both balances, in the
batch's transaction.

Audit: every AUDIT_EVERY_S seconds the worker checks the books in one snapshot: customer
accounts below zero, accounts whose balance isn't the sum of their entries, and whether all
balances still add up to zero. Logs JSON like the API; metrics on :9100. Tunables live in
config/worker.env, deployed with the code.
"""

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

import psycopg
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

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://ledger:ledger@postgres-db:5432/ledger")
HOUSE_ACCOUNT = 0
#: Settlement consumers (threads), and settlements each takes per transaction.
CONSUMERS = int(os.environ.get("CONSUMERS", "1"))
BATCH = int(os.environ.get("BATCH", "20"))
POLL_S = float(os.environ.get("POLL_S", "0.2"))
AUDIT_EVERY_S = float(os.environ.get("AUDIT_EVERY_S", "5"))

SETTLED = Counter("settlements_processed_total", "Settlements paid out", ["result"])
PENDING = Gauge("settlements_pending", "Settlements waiting to be paid out")
OLDEST = Gauge("settlements_oldest_seconds", "Age of the oldest pending settlement")
NEGATIVE = Gauge("ledger_negative_balances", "Customer accounts below zero")
ACCOUNTS_OFF = Gauge("ledger_accounts_off", "Accounts whose balance isn't the sum of entries")
BOOKS_OFF = Gauge("ledger_books_off_cents", "How far all balances are from adding up to zero")


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


def pay_out(conn: psycopg.Connection[Any], settlement: tuple[int, int, int]) -> None:
    """Moves one settlement's amount from the house's clearing balance to the merchant (the
    house's balance is debited once per batch, by settle_batch)."""
    settlement_id, merchant_id, amount = settlement
    row = conn.execute(
        "INSERT INTO transfers (from_account, to_account, amount_cents, kind)"
        " VALUES (%s, %s, %s, 'settlement') RETURNING id",
        (HOUSE_ACCOUNT, merchant_id, amount),
    ).fetchone()
    assert row is not None
    transfer_id = row[0]
    conn.execute(
        "INSERT INTO entries (transfer_id, account_id, amount_cents)"
        " VALUES (%s, %s, %s), (%s, %s, %s)",
        (transfer_id, merchant_id, amount, transfer_id, HOUSE_ACCOUNT, -amount),
    )
    conn.execute(
        "UPDATE accounts SET balance_cents = balance_cents + %s, updated_at = now() WHERE id = %s",
        (amount, merchant_id),
    )
    conn.execute(
        "UPDATE settlements SET status = 'settled', transfer_id = %s, settled_at = now()"
        " WHERE id = %s",
        (transfer_id, settlement_id),
    )


def settle_batch(conn: psycopg.Connection[Any]) -> int:
    """Pays out up to BATCH pending settlements in one transaction; returns how many."""
    with conn.transaction():
        batch = conn.execute(
            "SELECT id, merchant_id, amount_cents FROM settlements WHERE status = 'pending'"
            " ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED",
            (BATCH,),
        ).fetchall()
        # Credit merchants in id order, as transfers lock accounts: a batch and a transfer
        # between two merchants never take the same two locks in opposite orders.
        batch.sort(key=lambda settlement: settlement[1])
        for settlement in batch:
            pay_out(conn, settlement)
        if batch:
            # Every payment locks the house's row too: debit it once, last, so the batch
            # holds that lock for a moment instead of for the whole batch.
            conn.execute(
                "UPDATE accounts SET balance_cents = balance_cents - %s, updated_at = now()"
                " WHERE id = %s",
                (sum(settlement[2] for settlement in batch), HOUSE_ACCOUNT),
            )
    SETTLED.labels("paid").inc(len(batch))
    return len(batch)


def consume() -> None:
    while running:
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                while running:
                    if settle_batch(conn) < BATCH:
                        time.sleep(POLL_S)
        except psycopg.Error as exc:
            log.error("settlement failed, retrying", extra={"x_error": str(exc).strip()[:300]})
            SETTLED.labels("failed").inc()
            time.sleep(1)


AUDIT_SQL = """
SELECT
  (SELECT count(*) FROM accounts WHERE kind <> 'house' AND balance_cents < 0),
  (SELECT count(*) FROM accounts a
     LEFT JOIN (SELECT account_id, sum(amount_cents) AS total FROM entries GROUP BY account_id) e
       ON e.account_id = a.id
    WHERE a.balance_cents <> coalesce(e.total, 0)),
  (SELECT coalesce(sum(balance_cents), 0) FROM accounts),
  (SELECT count(*) FROM settlements WHERE status = 'pending'),
  (SELECT coalesce(extract(epoch FROM now() - min(created_at)), 0) FROM settlements
    WHERE status = 'pending')
"""


def audit() -> None:
    while running:
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                while running:
                    row = conn.execute(AUDIT_SQL).fetchone()
                    assert row is not None
                    negative, off, books, pending, oldest = row
                    NEGATIVE.set(negative)
                    ACCOUNTS_OFF.set(off)
                    BOOKS_OFF.set(abs(books))
                    PENDING.set(pending)
                    OLDEST.set(float(oldest))
                    if negative or off or books:
                        log.error(
                            "books don't balance",
                            extra={
                                "x_negative_accounts": negative,
                                "x_accounts_off": off,
                                "x_books_off_cents": books,
                            },
                        )
                    time.sleep(AUDIT_EVERY_S)
        except psycopg.Error as exc:
            log.error("audit failed, retrying", extra={"x_error": str(exc).strip()[:300]})
            time.sleep(2)


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    start_http_server(9100)
    log.info("started", extra={"x_consumers": CONSUMERS, "x_batch": BATCH})
    threads = [threading.Thread(target=consume, daemon=True) for _ in range(CONSUMERS)]
    threads.append(threading.Thread(target=audit, daemon=True))
    for thread in threads:
        thread.start()
    while running:
        time.sleep(0.5)
    # A deploy stops the worker: each consumer finishes its batch before the process exits.
    for thread in threads:
        thread.join(timeout=4)


if __name__ == "__main__":
    main()
