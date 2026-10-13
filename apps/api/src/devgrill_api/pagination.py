"""Opaque cursors for keyset pagination (docs/PLAN.md §10.1: `?cursor=&limit=`)."""

from __future__ import annotations

import base64
import json
from typing import Annotated, Any

from fastapi import Path, Query

from devgrill_api.errors import AppError

Limit = Annotated[int, Query(ge=1, le=100)]
#: Slugs in paths and filters. Constraining them keeps junk (and NUL bytes, which Postgres
#: rejects) out of queries and documents the format for clients.
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SlugPath = Annotated[str, Path(max_length=64, pattern=SLUG)]
SlugQuery = Annotated[str | None, Query(max_length=64, pattern=SLUG)]
HANDLE = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$"
HandlePath = Annotated[str, Path(max_length=39, pattern=HANDLE)]
#: Free-text search: printable text only (no control characters).
SearchQuery = Annotated[
    str | None, Query(min_length=2, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")
]
#: Opaque: echo back a `next_cursor` from a previous page. Base64url, so junk fails validation.
Cursor = Annotated[str | None, Query(max_length=512, pattern=r"^[A-Za-z0-9_-]+$")]


def encode(value: Any) -> str:
    raw = json.dumps(value, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(cursor: str) -> Any:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(400, "invalid_cursor", "The cursor is not valid.") from exc
