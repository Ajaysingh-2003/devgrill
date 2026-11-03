"""ShopKart product API. Small on purpose: every line is something an on-call engineer may
have to read at 2 a.m., so the read path is obvious and the metrics are honest."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis
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

from app import cache, db, logging_setup, orders_queue, settings
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
#: Each order's charged price against the product page the cache serves: a mismatch means a
#: shopper was shown one price and charged another. Orders of uncached products aren't counted.
PRICE_CHECKS = Counter(
    "checkout_price_checks_total", "Charged price versus the product page", ["result"]
)
#: Builds of the deals page, by outcome: ok, or timeout (cancelled by DEALS_TIMEOUT_MS).
DEALS_BUILDS = Counter("deals_builds_total", "Deals page builds", ["result"])
#: Signed-in page views, by whether the shopper's session was still there (ok) or not (missing).
SESSION_CHECKS = Counter("session_checks_total", "Session lookups", ["result"])
#: Order pages, by whether the order was there (found) or not (missing).
ORDER_LOOKUPS = Counter("order_lookups_total", "Order page lookups", ["result"])
# Four uvicorn processes share these through PROMETHEUS_MULTIPROC_DIR, so /metrics reports
# the whole service whichever process answers the scrape.
DB_POOL_IN_USE = Gauge(
    "db_pool_in_use", "Connections checked out of the pool", multiprocess_mode="livesum"
)
BUILD = Gauge("build_info", "Build", ["sha"], multiprocess_mode="max")
MEMORY = Gauge(
    "app_memory_bytes", "Resident memory of the API's workers", multiprocess_mode="livesum"
)
#: Memory that set a new high for its worker: flat once a healthy worker has warmed up,
#: climbing for as long as something leaks.
MEMORY_GROWTH = Counter("app_memory_growth_bytes", "New peak memory of the API's workers")
_PAGE_BYTES = os.sysconf("SC_PAGE_SIZE")
_memory_sampled_at = 0.0
_memory_peak = 0


def _sample_memory() -> None:
    """This worker's resident memory (and any new high), at most once a second."""
    global _memory_sampled_at, _memory_peak
    now = time.monotonic()
    if now - _memory_sampled_at < 1.0:
        return
    _memory_sampled_at = now
    try:
        # Resident minus shared: forked workers share pages, which a plain sum of RSS would
        # count once per worker.
        with open("/proc/self/statm", encoding="ascii") as statm:
            _, resident, shared, *_ = (int(f) for f in statm.read().split())
        private = (resident - shared) * _PAGE_BYTES
        MEMORY.set(private)
        if _memory_peak and private > _memory_peak:
            MEMORY_GROWTH.inc(private - _memory_peak)
        _memory_peak = max(_memory_peak, private)
    except OSError:
        pass


def _forget_dead_workers() -> None:
    """A worker the kernel killed never cleans up after itself: drop its live gauges, or
    the totals would keep counting it."""
    folder = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not folder:
        return
    for path in Path(folder).glob("gauge_live*_*.db"):
        try:
            pid = int(path.stem.rsplit("_", 1)[1])
            os.kill(pid, 0)
        except ProcessLookupError:
            multiprocess.mark_process_dead(pid, folder)
        except ValueError, PermissionError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _forget_dead_workers()
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
    _sample_memory()
    REQUESTS.labels(request.method, name, str(response.status_code)).inc()
    LATENCY.labels(name).observe(elapsed)
    if response.status_code >= 500 or elapsed > 1.0:
        log.warning(
            "slow or failed request",
            extra=fields(
                route=name,
                query=request.url.query[:200],
                status=response.status_code,
                ms=round(elapsed * 1000),
            ),
        )
    return response


@app.exception_handler(db.DatabaseBusy)
async def _busy(request: Request, exc: db.DatabaseBusy) -> JSONResponse:
    return JSONResponse({"error": "database busy, try again"}, status_code=503)


@app.exception_handler(pg_errors.LockNotAvailable)
async def _locked(request: Request, exc: pg_errors.LockNotAvailable) -> JSONResponse:
    log.warning("lock wait timed out", extra=fields(route=_route_name(request)))
    return JSONResponse({"error": "database busy, try again"}, status_code=503)


@app.exception_handler(pg_errors.QueryCanceled)
async def _cancelled(request: Request, exc: pg_errors.QueryCanceled) -> JSONResponse:
    log.error("query cancelled", extra=fields(route=_route_name(request), error=str(exc).strip()))
    return JSONResponse({"error": "the database took too long"}, status_code=503)


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


@app.get("/deals")
def deals() -> dict[str, Any]:
    """The sale landing page. Building it reads every review, so the cache holds a copy and
    keeps it fresh ahead of time: once the copy is DEALS_REFRESH_S old, the one request that
    claims the refresh rebuilds it while everyone else is served the copy. With no copy at all
    (a first deploy), the page is built on the spot."""
    page = cache.get_deals()
    if page is None:
        return _build_deals()
    stale = time.time() - float(page.get("built_at", 0)) > settings.DEALS_REFRESH_S
    if stale and cache.claim_deals_refresh():
        try:
            return _build_deals()
        except pg_errors.QueryCanceled:
            return page  # the copy is still good: try again on a later request
    return page


def _build_deals() -> dict[str, Any]:
    DB_QUERIES.labels("deals").inc()
    try:
        items = db.deals()
    except pg_errors.QueryCanceled:
        DEALS_BUILDS.labels("timeout").inc()
        raise
    DEALS_BUILDS.labels("ok").inc()
    page = {"built_at": time.time(), "items": items}
    cache.set_deals(page)
    return page


class SignIn(BaseModel):
    user_id: int = Field(ge=1)


@app.post("/sessions", status_code=201)
def sign_in(body: SignIn) -> Any:
    """Signs a shopper in (no passwords in this demo shop): a token for later requests."""
    token = cache.create_session(body.user_id)
    if token is None:
        return JSONResponse({"error": "sign-in is unavailable, try again"}, status_code=503)
    return {"token": token, "user_id": body.user_id}


@app.get("/me")
def me(request: Request) -> dict[str, Any]:
    """Who is signed in (every storefront page asks, for the header)."""
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    user_id = cache.session_user(token) if token else None
    if user_id is None:
        SESSION_CHECKS.labels("missing").inc()
        raise HTTPException(401, "signed out")
    SESSION_CHECKS.labels("ok").inc()
    return {"user_id": user_id}


@app.get("/users/{user_id}/orders/{order_id}")
def order_page(user_id: int, order_id: int) -> dict[str, Any]:
    """The order page shoppers land on after checkout, and come back to."""
    DB_QUERIES.labels("fetch_order").inc()
    order = db.fetch_order(user_id, order_id)
    if order is None:
        ORDER_LOOKUPS.labels("missing").inc()
        raise HTTPException(404, "no such order")
    ORDER_LOOKUPS.labels("found").inc()
    return order


class LikeIn(BaseModel):
    user_id: int = Field(ge=1)


@app.post("/products/{product_id}/likes", status_code=201)
def like_product(product_id: int, body: LikeIn) -> Any:
    try:
        cache.like(product_id, body.user_id)
    except redis.RedisError as exc:
        log.error("like not saved", extra=fields(product_id=product_id, error=type(exc).__name__))
        return JSONResponse({"error": "likes are unavailable, try again"}, status_code=503)
    return {"product_id": product_id, "liked": True}


@app.get("/products/{product_id}/likes")
def product_likes(product_id: int, user_id: int = 0) -> Any:
    """The heart on the product page: filled if this shopper likes it, and the count."""
    try:
        mine, count = cache.liked(product_id, user_id)
    except redis.RedisError as exc:
        log.error(
            "likes unavailable", extra=fields(product_id=product_id, error=type(exc).__name__)
        )
        return JSONResponse({"error": "likes are unavailable, try again"}, status_code=503)
    return {"product_id": product_id, "liked": mine, "count": count}


class OrderIn(BaseModel):
    user_id: int = Field(ge=1)
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=20)


@app.post("/orders", status_code=201)
def place_order(body: OrderIn) -> dict[str, Any]:
    DB_QUERIES.labels("create_order").inc()
    try:
        order = db.create_order(body.user_id, body.product_id, body.quantity)
    except LookupError:
        raise HTTPException(404, "no such product") from None
    _check_price(order, body.product_id, body.quantity)
    orders_queue.enqueue(order, body.product_id, body.quantity)
    return order


def _check_price(order: dict[str, Any], product_id: int, quantity: int) -> None:
    shown = cache.get(product_id)
    if shown is None:
        return
    same = shown.get("price_cents", 0) * quantity == order["total_cents"]
    PRICE_CHECKS.labels("match" if same else "mismatch").inc()


@app.get("/users/{user_id}/orders")
def user_orders(user_id: int) -> list[dict[str, Any]]:
    DB_QUERIES.labels("fetch_orders").inc()
    return db.fetch_orders_for_user(user_id)


@app.get("/products/{product_id}/also-bought")
def product_also_bought(product_id: int, user_id: int = 0) -> dict[str, Any]:
    """The product page's "customers also bought" box, behind a flag rolled out by user."""
    if not settings.also_bought_for(user_id):
        return {"enabled": False, "items": []}
    DB_QUERIES.labels("also_bought").inc()
    return {"enabled": True, "items": db.also_bought(product_id)}
