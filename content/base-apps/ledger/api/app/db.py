"""Postgres access through a connection pool (psycopg 3). Every movement of money is one
transaction: a transfer row, two entries that sum to zero, and both balances."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from prometheus_client import Counter
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app import settings
from app.logging_setup import fields

log = logging.getLogger("db")

#: Debits that left a customer's wallet below zero. Never meant to happen.
OVERDRAFTS = Counter("ledger_overdrafts_total", "Debits that took a wallet below zero")


class DatabaseBusy(Exception):
    """No connection became free within the pool timeout."""


class InsufficientFunds(Exception):
    """The payer's balance doesn't cover the amount."""


pool = ConnectionPool(
    settings.DATABASE_URL,
    min_size=settings.DB_POOL_MIN,
    max_size=settings.DB_POOL_MAX,
    timeout=settings.DB_POOL_TIMEOUT_S,
    kwargs={"row_factory": dict_row},
    open=False,
)


@contextmanager
def connection() -> Iterator[Connection[dict[str, Any]]]:
    try:
        with pool.connection() as conn:
            yield conn
    except PoolTimeout as exc:
        log.error("pool exhausted", extra=fields(pool_max=settings.DB_POOL_MAX))
        raise DatabaseBusy() from exc


def account(account_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        return conn.execute(
            "SELECT id, owner, kind, balance_cents, updated_at FROM accounts WHERE id = %s",
            (account_id,),
        ).fetchone()


def _move(
    conn: Connection[dict[str, Any]], from_id: int, to_id: int, amount: int, kind: str
) -> dict[str, Any]:
    """Moves `amount` from one account to another inside the caller's transaction."""
    # Lock both accounts, always in id order: two transfers in opposite directions take the
    # locks in the same order, so neither can hold one row while waiting for the other, and
    # the balance read here can't change before the debit below.
    rows = conn.execute(
        "SELECT id, kind, balance_cents FROM accounts WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
        ([from_id, to_id],),
    ).fetchall()
    accounts = {row["id"]: row for row in rows}
    if from_id not in accounts or to_id not in accounts:
        raise LookupError("account")
    payer = accounts[from_id]
    if payer["kind"] != "house" and payer["balance_cents"] < amount:
        raise InsufficientFunds()
    transfer = conn.execute(
        "INSERT INTO transfers (from_account, to_account, amount_cents, kind)"
        " VALUES (%s, %s, %s, %s) RETURNING id, from_account, to_account, amount_cents, kind,"
        " created_at",
        (from_id, to_id, amount, kind),
    ).fetchone()
    assert transfer is not None
    conn.execute(
        "INSERT INTO entries (transfer_id, account_id, amount_cents)"
        " VALUES (%s, %s, %s), (%s, %s, %s)",
        (transfer["id"], to_id, amount, transfer["id"], from_id, -amount),
    )
    debited = conn.execute(
        "UPDATE accounts SET balance_cents = balance_cents - %s, updated_at = now() WHERE id = %s"
        " RETURNING kind, balance_cents",
        (amount, from_id),
    ).fetchone()
    if debited and debited["kind"] != "house" and debited["balance_cents"] < 0:
        OVERDRAFTS.inc()
        log.error(
            "wallet overdrawn",
            extra=fields(account_id=from_id, balance_cents=debited["balance_cents"]),
        )
    conn.execute(
        "UPDATE accounts SET balance_cents = balance_cents + %s, updated_at = now() WHERE id = %s",
        (amount, to_id),
    )
    return transfer


def transfer(from_id: int, to_id: int, amount: int) -> dict[str, Any]:
    with connection() as conn, conn.transaction():
        return _move(conn, from_id, to_id, amount, "transfer")


def pay(customer_id: int, merchant_id: int, amount: int) -> dict[str, Any]:
    """A card payment: the customer is debited now (into the house's clearing balance), and the
    merchant is paid out later by the worker's settlement run."""
    with connection() as conn, conn.transaction():
        merchant = conn.execute(
            "SELECT id FROM accounts WHERE id = %s AND kind = 'merchant'", (merchant_id,)
        ).fetchone()
        if merchant is None:
            raise LookupError("merchant")
        payment = _move(conn, customer_id, settings.HOUSE_ACCOUNT, amount, "payment")
        conn.execute(
            "INSERT INTO settlements (merchant_id, amount_cents) VALUES (%s, %s)",
            (merchant_id, amount),
        )
        return payment


def healthy() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
