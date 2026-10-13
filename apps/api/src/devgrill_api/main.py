"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from devgrill import __version__
from devgrill.config import BRAND_NAME, Settings, get_settings
from devgrill.infra import cache, db
from devgrill.observability import configure_logging, configure_sentry, configure_tracing
from devgrill_api import health
from devgrill_api.errors import install_error_handlers
from devgrill_api.middleware import RequestIdMiddleware

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    app.state.engine = db.create_engine(settings)
    app.state.valkey = cache.create_valkey(settings)
    app.state.temporal = None  # connected lazily by the readiness check / first workflow call
    log.info("api_started", env=settings.env, version=__version__)
    try:
        yield
    finally:
        await app.state.valkey.aclose()
        await app.state.engine.dispose()
        log.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    configure_sentry(settings)

    app = FastAPI(
        title=f"{BRAND_NAME} API",
        version=__version__,
        description="DevGrill platform API. Errors use RFC 9457 application/problem+json.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)

    app.include_router(health.router)
    # Versioned resource routers (/v1/...) arrive in phase 2.

    configure_tracing(settings, service_name="devgrill-api", app=app)
    return app
