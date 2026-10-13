"""Liveness and readiness probes."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from devgrill import __version__
from devgrill.infra import cache, db, workflows

router = APIRouter(tags=["health"])

Check = Callable[[Request], Awaitable[None]]


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = __version__


class CheckResult(BaseModel):
    ok: bool
    latency_ms: float
    error: str | None = None


class Readiness(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, CheckResult]


async def _check_database(request: Request) -> None:
    await db.ping(request.app.state.engine)


async def _check_valkey(request: Request) -> None:
    await cache.ping(request.app.state.valkey)


async def _check_temporal(request: Request) -> None:
    state = request.app.state
    if getattr(state, "temporal", None) is None:
        state.temporal = await workflows.connect_temporal(state.settings)
    await workflows.ping(state.temporal)


READINESS_CHECKS: dict[str, Check] = {
    "database": _check_database,
    "valkey": _check_valkey,
    "temporal": _check_temporal,
}


async def _run(check: Check, request: Request, timeout_s: float) -> CheckResult:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_s):
            await check(request)
    except Exception as exc:  # readiness must report, never raise
        return CheckResult(
            ok=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            error=type(exc).__name__,
        )
    return CheckResult(ok=True, latency_ms=round((time.perf_counter() - started) * 1000, 1))


@router.get("/healthz", response_model=Health, summary="Liveness probe")
async def healthz() -> Health:
    return Health()


@router.get(
    "/readyz",
    response_model=Readiness,
    summary="Readiness probe (database, Valkey, Temporal)",
    responses={503: {"model": Readiness, "description": "A dependency is unavailable"}},
)
async def readyz(request: Request) -> JSONResponse:
    timeout_s = request.app.state.settings.readiness_timeout_s
    names = list(READINESS_CHECKS)
    results = await asyncio.gather(
        *(_run(READINESS_CHECKS[name], request, timeout_s) for name in names)
    )
    checks = dict(zip(names, results, strict=True))
    ready = all(result.ok for result in results)
    body = Readiness(status="ok" if ready else "degraded", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ready else 503)
