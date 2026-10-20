"""The API's client for the gateway's internal sandbox operations (ADR 014).

Requests are signed (HMAC over method, path, query and body; `devgrill.infra.signing`). The
gateway's refusals come back as AppErrors with its status and code, so the browser gets the
same problem+json as for any API error. Tests swap in a fake via `app.state.gateway`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx2

from devgrill.config import Settings
from devgrill.infra.signing import signed_headers
from devgrill_api.errors import AppError


class Gateway(Protocol):
    async def call(
        self,
        method: str,
        attempt_id: uuid.UUID,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class HttpGateway:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.gateway_internal_url.rstrip("/")
        self._secret = settings.internal_hmac_secret
        self._client = httpx2.AsyncClient(timeout=httpx2.Timeout(180, connect=5))

    async def call(
        self,
        method: str,
        attempt_id: uuid.UUID,
        path: str,
        *,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = f"/internal/attempts/{attempt_id}/{path}"
        params = {k: v for k, v in (query or {}).items() if v is not None}
        if params:
            target += f"?{urlencode(params)}"
        content = json.dumps(body).encode() if body is not None else b""
        headers = signed_headers(self._secret, method, target, content)
        if body is not None:
            headers["content-type"] = "application/json"
        try:
            res = await self._client.request(
                method, self._base + target, content=content, headers=headers
            )
        except httpx2.HTTPError as exc:
            raise AppError(
                503,
                "gateway_unavailable",
                "The sandbox gateway is unreachable.",
                headers={"Retry-After": "5"},
            ) from exc
        data: dict[str, Any] = res.json() if res.content else {}
        if res.status_code >= 400:
            status = res.status_code if res.status_code in (400, 404, 409, 413, 415) else 502
            raise AppError(
                status, str(data.get("code", "sandbox_error")), str(data.get("detail", ""))
            )
        return data

    async def close(self) -> None:
        await self._client.aclose()
