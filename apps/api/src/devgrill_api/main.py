"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from devgrill import __version__
from devgrill.config import BRAND_NAME, Settings, get_settings
from devgrill.infra import cache, db
from devgrill.observability import configure_logging, configure_sentry, configure_tracing
from devgrill_api import health
from devgrill_api.auth.jwks import JwksCache, http_fetcher
from devgrill_api.errors import PROBLEM_RESPONSES, Problem, install_error_handlers
from devgrill_api.idempotency import IdempotencyMiddleware
from devgrill_api.middleware import RequestIdMiddleware
from devgrill_api.ratelimit import rate_limit
from devgrill_api.routers import admin, attempts, catalog, debrief, internal, me, workspace

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    app.state.engine = db.create_engine(settings)
    app.state.session_factory = db.create_session_factory(app.state.engine)
    app.state.valkey = cache.create_valkey(settings)
    if getattr(app.state, "jwks", None) is None:  # tests inject their own key set
        app.state.jwks = JwksCache(
            http_fetcher(settings.auth_jwks_url),
            ttl_s=settings.auth_jwks_ttl_s,
            min_refresh_s=settings.auth_jwks_min_refresh_s,
        )
    app.state.temporal = None  # connected lazily by the readiness check / first workflow call
    log.info("api_started", env=settings.env, version=__version__)
    try:
        yield
    finally:
        if getattr(app.state, "gateway", None) is not None and hasattr(app.state.gateway, "close"):
            await app.state.gateway.close()
        await app.state.valkey.aclose()
        await app.state.engine.dispose()
        log.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.require_secrets()
    configure_logging(settings)
    configure_sentry(settings)

    app = FastAPI(
        title=f"{BRAND_NAME} API",
        version=__version__,
        description="DevGrill platform API. Errors use RFC 9457 application/problem+json.",
        lifespan=lifespan,
        # operationId = handler name, so the generated client reads `listTracks`, not
        # `listTracksV1TracksGet`. Handler names must therefore be unique (checked in tests).
        generate_unique_id_function=lambda route: route.name,
    )
    app.state.settings = settings

    # Middleware runs outermost-last: request id -> CORS -> idempotency -> routes.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(
        CORSMiddleware,
        # Only the web origin. Browsers send a Bearer token, never cookies, so no credentials.
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "authorization",
            "content-type",
            "idempotency-key",
            "x-guest-token",
            "x-request-id",
        ],
        expose_headers=["x-request-id", "ratelimit", "ratelimit-policy", "retry-after"],
        max_age=600,
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)

    app.include_router(health.router)
    v1 = APIRouter(
        prefix="/v1", dependencies=[Depends(rate_limit("default"))], responses=PROBLEM_RESPONSES
    )
    for module in (catalog, me, admin, attempts, workspace, debrief):
        v1.include_router(module.router)
    app.include_router(v1)
    app.include_router(internal.router)

    _register_problem_schema(app)
    configure_tracing(settings, service_name="devgrill-api", app=app)
    return app


def _register_problem_schema(app: FastAPI) -> None:
    """Add the Problem schema the error responses reference (FastAPI only adds models it sees)."""
    original = app.openapi

    def openapi() -> dict[str, object]:
        if app.openapi_schema is None:
            schema = original()
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            components.update(
                {
                    name: definition
                    for name, definition in Problem.model_json_schema(
                        ref_template="#/components/schemas/{model}"
                    )
                    .get("$defs", {})
                    .items()
                }
            )
            problem = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
            problem.pop("$defs", None)
            components["Problem"] = problem
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
