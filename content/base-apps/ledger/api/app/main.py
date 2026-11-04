"""Ledger payments API: wallets, transfers and card payments. Small on purpose: every line is
something an on-call engineer may have to read at 2 a.m., and the money has to add up."""

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

from app import db, logging_setup, settings
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
#: Money movements by outcome: ok, insufficient (refused), or failed.
MOVEMENTS = Counter("ledger_movements_total", "Transfers and payments", ["kind", "result"])
# Four uvicorn processes share these through PROMETHEUS_MULTIPROC_DIR.
DB_POOL_IN_USE = Gauge(
    "db_pool_in_use", "Connections checked out of the pool", multiprocess_mode="livesum"
)
BUILD = Gauge("build_info", "Build", ["sha"], multiprocess_mode="max")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    BUILD.labels(sha=settings.GIT_SHA).set(1)
    db.pool.open()
    log.info("started", extra=fields(sha=settings.GIT_SHA))
    try:
        yield
    finally:
        db.pool.close()


app = FastAPI(title="Ledger", lifespan=lifespan)


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


@app.exception_handler(pg_errors.DeadlockDetected)
async def _deadlock(request: Request, exc: pg_errors.DeadlockDetected) -> JSONResponse:
    log.error("deadlock detected", extra=fields(route=_route_name(request), error=str(exc).strip()))
    return JSONResponse({"error": "the transfer failed, try again"}, status_code=503)


@app.exception_handler(pg_errors.QueryCanceled)
async def _cancelled(request: Request, exc: pg_errors.QueryCanceled) -> JSONResponse:
    log.error("query cancelled", extra=fields(route=_route_name(request), error=str(exc).strip()))
    return JSONResponse({"error": "the database took too long"}, status_code=503)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", "sha": settings.GIT_SHA}


@app.get("/readyz")
def readyz() -> JSONResponse:
    ok = db.healthy()
    return JSONResponse({"database": ok}, status_code=200 if ok else 503)


@app.get("/metrics")
def metrics() -> Response:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


@app.get("/accounts/{account_id}")
def get_account(account_id: int) -> dict[str, Any]:
    account = db.account(account_id)
    if account is None:
        raise HTTPException(404, "no such account")
    return account


class TransferIn(BaseModel):
    from_account: int = Field(ge=0)
    to_account: int = Field(ge=0)
    amount_cents: int = Field(gt=0, le=10_000_000)


@app.post("/transfers", status_code=201)
def create_transfer(body: TransferIn) -> dict[str, Any]:
    if body.from_account == body.to_account:
        raise HTTPException(422, "an account can't pay itself")
    return _record(
        "transfer", lambda: db.transfer(body.from_account, body.to_account, body.amount_cents)
    )


class PaymentIn(BaseModel):
    account_id: int = Field(ge=1)
    merchant_id: int = Field(ge=1)
    amount_cents: int = Field(gt=0, le=10_000_000)


@app.post("/payments", status_code=201)
def create_payment(body: PaymentIn) -> dict[str, Any]:
    return _record("payment", lambda: db.pay(body.account_id, body.merchant_id, body.amount_cents))


def _record(kind: str, move: Any) -> dict[str, Any]:
    try:
        result: dict[str, Any] = move()
    except LookupError:
        MOVEMENTS.labels(kind, "refused").inc()
        raise HTTPException(404, "no such account") from None
    except db.InsufficientFunds:
        MOVEMENTS.labels(kind, "insufficient").inc()
        raise HTTPException(409, "insufficient funds") from None
    except Exception:
        MOVEMENTS.labels(kind, "failed").inc()
        raise
    MOVEMENTS.labels(kind, "ok").inc()
    return result
