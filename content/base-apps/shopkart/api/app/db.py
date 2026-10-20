"""Postgres access through a connection pool (psycopg 3)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app import settings
from app.logging_setup import fields

log = logging.getLogger("db")


class DatabaseBusy(Exception):
    """No connection became free within the pool timeout."""


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


def fetch_product(product_id: int) -> dict[str, Any] | None:
    """The product page: the product plus its rating summary (the expensive part)."""
    with connection() as conn:
        return conn.execute(
            "SELECT p.id, p.sku, p.name, p.description, p.price_cents, p.stock, p.category,"
            " p.updated_at, r.rating_avg, r.rating_count"
            " FROM products p CROSS JOIN LATERAL ("
            "   SELECT round(avg(rating), 2)::float AS rating_avg, count(*) AS rating_count"
            "   FROM reviews WHERE product_id = p.id) r"
            " WHERE p.id = %s",
            (product_id,),
        ).fetchone()


def search_products(query: str, limit: int = 20) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            "SELECT id, sku, name, price_cents, category FROM products"
            " WHERE name ILIKE %s ORDER BY id LIMIT %s",
            (f"%{query}%", limit),
        ).fetchall()


def fetch_orders_for_user(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            "SELECT id, user_id, status, total_cents, created_at FROM orders"
            " WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit),
        ).fetchall()


def create_order(user_id: int, product_id: int, quantity: int) -> dict[str, Any]:
    with connection() as conn, conn.transaction():
        product = conn.execute(
            "SELECT price_cents FROM products WHERE id = %s", (product_id,)
        ).fetchone()
        if product is None:
            raise LookupError("product")
        return conn.execute(
            "INSERT INTO orders (user_id, product_id, quantity, total_cents, status)"
            " VALUES (%s, %s, %s, %s, 'pending')"
            " RETURNING id, user_id, status, total_cents, created_at",
            (user_id, product_id, quantity, product["price_cents"] * quantity),
        ).fetchone()


def update_price(product_id: int, price_cents: int) -> bool:
    with connection() as conn:
        result = conn.execute(
            "UPDATE products SET price_cents = %s, updated_at = now() WHERE id = %s",
            (price_cents, product_id),
        )
        return result.rowcount == 1


def healthy() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
