"""JSON logs on stdout, one object per line, so the Logs panel can filter by field."""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from app import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": settings.SERVICE_NAME,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("x_"):
                entry[key[2:]] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, separators=(",", ":"))


def configure() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # uvicorn's access log duplicates our request log; keep its errors only.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)


def fields(**values: Any) -> dict[str, Any]:
    """`log.info("cache miss", extra=fields(product_id=42))` -> a `product_id` JSON field."""
    return {f"x_{key}": value for key, value in values.items()}
