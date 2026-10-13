"""Structured logging plus optional OpenTelemetry and Sentry hooks (off by default)."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from devgrill.config import Settings


def configure_logging(settings: Settings) -> None:
    """Route stdlib and structlog output through one renderer.

    `log_format=json` for anything machine-read (CI, containers); `console` for local dev.
    Context such as request_id / attempt_id is bound with structlog.contextvars.
    """
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def configure_tracing(settings: Settings, service_name: str, app: Any | None = None) -> bool:
    """Enable OpenTelemetry when OTEL_ENABLED=true and the `otel` extra is installed.

    Returns True when tracing was enabled.
    """
    if not settings.otel_enabled:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        structlog.get_logger(__name__).warning(
            "otel_enabled_but_not_installed", hint="uv sync --extra otel"
        )
        return False

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    return True


def configure_sentry(settings: Settings) -> bool:
    """Enable Sentry when SENTRY_DSN is set and the `sentry` extra is installed."""
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        structlog.get_logger(__name__).warning("sentry_dsn_set_but_not_installed")
        return False
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.0)
    return True
