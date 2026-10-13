import logging

import pytest
import structlog

from devgrill.config import Settings
from devgrill.observability import configure_logging, configure_sentry, configure_tracing


def test_json_logging_renders_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(_env_file=None, log_format="json"))  # type: ignore[call-arg]
    with structlog.contextvars.bound_contextvars(request_id="abc123"):
        structlog.get_logger("t").info("hello", answer=42)
    err = capsys.readouterr().err
    assert '"event": "hello"' in err
    assert '"request_id": "abc123"' in err
    assert '"answer": 42' in err


def test_stdlib_logs_use_same_pipeline(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(_env_file=None, log_format="json"))  # type: ignore[call-arg]
    logging.getLogger("plain").warning("from stdlib")
    assert '"event": "from stdlib"' in capsys.readouterr().err


def test_tracing_and_sentry_off_by_default() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert configure_tracing(settings, service_name="test") is False
    assert configure_sentry(settings) is False
