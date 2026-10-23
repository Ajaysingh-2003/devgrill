"""The sandbox gateway (ADR 014): terminal and telemetry WebSockets, sandbox operations.

- `/gw/v1/attempts/{id}/terminal` and `/telemetry`: browser WebSockets, single-use tickets.
- `/internal/attempts/{id}/...`: sandbox operations for the API (files, deploys, rollbacks,
  restarts, database and cache insights), signed with INTERNAL_HMAC_SECRET (method, path and
  body), never exposed to browsers.
- The control bridge answers the in-sandbox `devgrill` CLI.

The gateway is the only platform service with Docker access besides the worker; on a hosted
fleet it runs on each sandbox host.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, FastAPI, Query, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from devgrill import __version__
from devgrill.config import Settings, get_settings
from devgrill.infra import cache, db
from devgrill.infra.events import EventRecorder
from devgrill.infra.objectstore import ObjectStore
from devgrill.infra.signing import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    SignatureError,
    verify_request,
)
from devgrill.observability import configure_logging
from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.driver import SandboxError
from devgrill_gateway.channels import Channels
from devgrill_gateway.control import ControlBridges
from devgrill_gateway.operations import OperationError, Operations

log = structlog.get_logger(__name__)

PROBE_BUILD_DIR = Path("infra/sandbox/probe")
#: Built from source in a checkout; pulled (prebuilt) elsewhere.
HAVE_PROBE_SOURCE = PROBE_BUILD_DIR.is_dir()


class _UnauthorizedError(Exception):
    pass


async def signed(request: Request) -> None:
    """Only the API may call /internal: HMAC over method, path, query and body."""
    settings: Settings = request.app.state.settings
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    try:
        verify_request(
            settings.internal_hmac_secret,
            request.headers.get(TIMESTAMP_HEADER),
            request.headers.get(SIGNATURE_HEADER),
            request.method,
            target,
            await request.body(),
        )
    except SignatureError as exc:
        raise _UnauthorizedError(str(exc)) from exc


class FileIn(BaseModel):
    content: str = Field(max_length=256 * 1024)


class DeployIn(BaseModel):
    service: str | None = Field(default=None, max_length=40)


class RollbackIn(BaseModel):
    service: str | None = Field(default=None, max_length=40)
    ref: str = Field(min_length=4, max_length=40)


class RestartIn(BaseModel):
    service: str = Field(max_length=40)


class QueryIn(BaseModel):
    sql: str = Field(min_length=1, max_length=4000)


def _ops(request: Request) -> Operations:
    ops: Operations = request.app.state.ops
    return ops


def internal_router() -> APIRouter:
    router = APIRouter(prefix="/internal/attempts/{attempt_id}", dependencies=[Depends(signed)])

    @router.get("/status")
    async def status(attempt_id: uuid.UUID, request: Request) -> dict[str, Any]:
        return await _ops(request).status(attempt_id)

    @router.get("/files")
    async def files(
        attempt_id: uuid.UUID, request: Request, service: str | None = None
    ) -> dict[str, Any]:
        return await _ops(request).files(attempt_id, service)

    @router.get("/file")
    async def read_file(
        attempt_id: uuid.UUID,
        request: Request,
        path: str = Query(max_length=300),
        service: str | None = None,
    ) -> dict[str, Any]:
        return await _ops(request).read_file(attempt_id, service, path)

    @router.put("/file")
    async def write_file(
        attempt_id: uuid.UUID,
        body: FileIn,
        request: Request,
        path: str = Query(max_length=300),
        service: str | None = None,
    ) -> dict[str, Any]:
        return await _ops(request).write_file(attempt_id, service, path, body.content)

    @router.get("/deploys")
    async def deploys(
        attempt_id: uuid.UUID, request: Request, service: str | None = None
    ) -> dict[str, Any]:
        return await _ops(request).deploys(attempt_id, service)

    @router.get("/deploys/{sha}")
    async def deploy_changes(
        attempt_id: uuid.UUID, sha: str, request: Request, service: str | None = None
    ) -> dict[str, Any]:
        return await _ops(request).deploy_changes(attempt_id, service, sha)

    @router.post("/deploys")
    async def deploy(attempt_id: uuid.UUID, body: DeployIn, request: Request) -> dict[str, Any]:
        return await _ops(request).deploy(attempt_id, body.service, "ui")

    @router.post("/rollbacks")
    async def rollback(attempt_id: uuid.UUID, body: RollbackIn, request: Request) -> dict[str, Any]:
        return await _ops(request).rollback(attempt_id, body.service, body.ref, "ui")

    @router.post("/restarts")
    async def restart(attempt_id: uuid.UUID, body: RestartIn, request: Request) -> dict[str, Any]:
        return await _ops(request).restart(attempt_id, body.service, "ui")

    @router.get("/db")
    async def database(attempt_id: uuid.UUID, request: Request) -> dict[str, Any]:
        return await _ops(request).db(attempt_id)

    @router.post("/db/query")
    async def query(attempt_id: uuid.UUID, body: QueryIn, request: Request) -> dict[str, Any]:
        return await _ops(request).db_query(attempt_id, body.sql)

    @router.get("/cache")
    async def cache_view(attempt_id: uuid.UUID, request: Request) -> dict[str, Any]:
        return await _ops(request).cache(attempt_id)

    return router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = db.create_engine(settings)
    session_factory = db.create_session_factory(engine)
    valkey = cache.create_valkey(settings)
    driver = getattr(app.state, "driver", None) or ComposeDriver(
        probe_image=settings.sandbox_probe_image,
        probe_build_dir=PROBE_BUILD_DIR if HAVE_PROBE_SOURCE else None,
    )
    recorder = EventRecorder(session_factory, valkey)
    ops = Operations(
        driver=driver,
        session_factory=session_factory,
        recorder=recorder,
        content_root=settings.content_root,
    )
    bridges = ControlBridges(ops)
    app.state.ops = ops
    app.state.valkey = valkey
    app.state.channels = Channels(
        settings=settings,
        ops=ops,
        bridges=bridges,
        valkey=valkey,
        store=getattr(app.state, "store", None) or ObjectStore.from_settings(settings),
    )
    log.info("gateway_started", version=__version__)
    try:
        yield
    finally:
        await bridges.close()
        await driver.close()
        await valkey.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    app = FastAPI(
        title="DevGrill Gateway", version=__version__, lifespan=lifespan, openapi_url=None
    )
    app.state.settings = settings

    @app.exception_handler(_UnauthorizedError)
    async def _unauthorized(request: Request, exc: _UnauthorizedError) -> JSONResponse:
        return JSONResponse({"code": "unauthorized", "detail": str(exc)}, status_code=401)

    @app.exception_handler(OperationError)
    async def _operation(request: Request, exc: OperationError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "detail": exc.detail}, status_code=exc.status)

    @app.exception_handler(SandboxError)
    async def _sandbox(request: Request, exc: SandboxError) -> JSONResponse:
        log.warning("gateway.sandbox_error", path=request.url.path, error=str(exc)[:500])
        return JSONResponse({"code": "sandbox_error", "detail": str(exc)[:500]}, status_code=502)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.websocket("/gw/v1/attempts/{attempt_id}/terminal")
    async def terminal(
        websocket: WebSocket,
        attempt_id: uuid.UUID,
        ticket: str = "",
        cols: int = 120,
        rows: int = 32,
    ) -> None:
        await websocket.app.state.channels.terminal(websocket, attempt_id, ticket, cols, rows)

    @app.websocket("/gw/v1/attempts/{attempt_id}/telemetry")
    async def telemetry(websocket: WebSocket, attempt_id: uuid.UUID, ticket: str = "") -> None:
        await websocket.app.state.channels.telemetry(websocket, attempt_id, ticket)

    app.include_router(internal_router())
    return app
