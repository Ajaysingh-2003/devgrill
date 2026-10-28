"""ShopKart product API. Small on purpose: every line is something an on-call engineer may
have to read at 2 a.m., so the read path is obvious and the metrics are honest."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from psycopg import errors as pg_errors
from pydantic import BaseModel, Field

from app import cache, db, logging_setup, settings
from app.logging_setup import fields

logging_setup.configure()
log = logging.getLogger("api")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency",
    ["route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
CACHE_OPS = Counter("product_cache_total", "Product cache lookups", ["result"])
DB_QUERIES = Counter("db_queries_total", "Database queries", ["query"])
# Four uvicorn processes share these through PROMETHEUS_MULTIPROC_DIR, so /metrics reports
# the whole service whichever process answers the scrape.
DB_POOL_IN_USE = Gauge(
    "db_pool_in_use", "Connections checked out of the pool", multiprocess_mode="livesum"
)
BUILD = Gauge("build_info", "Build", ["sha"], multiprocess_mode="max")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    BUILD.labels(sha=settings.GIT_SHA).set(1)
    db.pool.open()
    log.info("started", extra=fields(sha=settings.GIT_SHA, cache_ttl=settings.CACHE_TTL_SECONDS))
    try:
        yield
    finally:
        db.pool.close()


app = FastAPI(title="ShopKart", lifespan=lifespan)


def _route_name(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


@app.middleware("http")
async def observe(request: Request, call_next: Any) -> Response:
    started = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        name = _route_name(request)
        REQUESTS.labels(request.method, name, "500").inc()
        LATENCY.labels(name).observe(time.perf_counter() - started)
        log.exception("request failed", extra=fields(route=name))
        raise
    # The route is known only after routing: label by template, never by raw path.
    name = _route_name(request)
    elapsed = time.perf_counter() - started
    stats = db.pool.get_stats()
    DB_POOL_IN_USE.set(stats.get("pool_size", 0) - stats.get("pool_available", 0))
    REQUESTS.labels(request.method, name, str(response.status_code)).inc()
    LATENCY.labels(name).observe(elapsed)
    if response.status_code >= 500 or elapsed > 1.0:
        log.warning(
            "slow or failed request",
            extra=fields(route=name, status=response.status_code, ms=round(elapsed * 1000)),
        )
    return response


@app.exception_handler(db.DatabaseBusy)
async def _busy(request: Request, exc: db.DatabaseBusy) -> JSONResponse:
    return JSONResponse({"error": "database busy, try again"}, status_code=503)


@app.exception_handler(pg_errors.LockNotAvailable)
async def _locked(request: Request, exc: pg_errors.LockNotAvailable) -> JSONResponse:
    log.warning("lock wait timed out", extra=fields(route=_route_name(request)))
    return JSONResponse({"error": "database busy, try again"}, status_code=503)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "sha": settings.GIT_SHA}


@app.get("/readyz")
def readyz() -> JSONResponse:
    checks = {"database": db.healthy(), "cache": cache.healthy()}
    return JSONResponse(checks, status_code=200 if all(checks.values()) else 503)


@app.get("/metrics")
def metrics() -> Response:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@app.get("/products/{product_id}")
def get_product(product_id: int) -> dict[str, Any]:
    product = cache.get(product_id)
    if product is not None:
        CACHE_OPS.labels("hit").inc()
        return product
    CACHE_OPS.labels("miss").inc()
    DB_QUERIES.labels("fetch_product").inc()
    product = db.fetch_product(product_id)
    if product is None:
        raise HTTPException(404, "no such product")
    cache.set(product_id, product)
    return product


@app.get("/products")
def search(q: str = "", limit: int = 20) -> list[dict[str, Any]]:
    DB_QUERIES.labels("search_products").inc()
    return db.search_products(q, min(limit, 100))


class PriceUpdate(BaseModel):
    price_cents: int = Field(ge=0)


@app.put("/products/{product_id}/price")
def set_price(product_id: int, body: PriceUpdate) -> dict[str, Any]:
    DB_QUERIES.labels("update_price").inc()
    if not db.update_price(product_id, body.price_cents):
        raise HTTPException(404, "no such product")
    cache.invalidate(product_id)
    return {"id": product_id, "price_cents": body.price_cents}


class OrderIn(BaseModel):
    user_id: int = Field(ge=1)
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=20)


@app.post("/orders", status_code=201)
def place_order(body: OrderIn) -> dict[str, Any]:
    DB_QUERIES.labels("create_order").inc()
    try:
        return db.create_order(body.user_id, body.product_id, body.quantity)
    except LookupError:
        raise HTTPException(404, "no such product") from None


@app.get("/users/{user_id}/orders")
def user_orders(user_id: int) -> list[dict[str, Any]]:
    DB_QUERIES.labels("fetch_orders").inc()
    return db.fetch_orders_for_user(user_id)
