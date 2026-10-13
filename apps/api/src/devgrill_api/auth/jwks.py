"""Verify Better Auth JWTs (EdDSA) against a cached, rotating JWKS (ADR 005)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx2
import jwt
import structlog
from jwt import PyJWK

log = structlog.get_logger(__name__)

#: Only EdDSA is accepted. Never let the token pick its own algorithm ("alg confusion").
ALGORITHMS = ["EdDSA"]
#: Clock skew tolerated between the web server (signer) and the API.
LEEWAY_S = 30

FetchJwks = Callable[[], Awaitable[dict[str, Any]]]


class TokenError(Exception):
    """The token is missing, malformed, expired, for someone else, or signed by an unknown key."""


@dataclass(frozen=True, slots=True)
class Claims:
    sub: str
    email: str | None
    name: str | None
    login: str | None
    image: str | None
    raw: dict[str, Any]


def http_fetcher(url: str, timeout_s: float = 3.0) -> FetchJwks:
    async def fetch() -> dict[str, Any]:
        async with httpx2.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(url, headers={"accept": "application/json"})
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    return fetch


class JwksCache:
    """Keys by `kid`, refreshed on a TTL and, rate-limited, whenever an unknown `kid` appears.

    The second rule is what makes key rotation seamless: the first token signed with a new
    key forces one refetch; a flood of tokens with made-up kids can't force more than one
    fetch per `min_refresh_s`.
    """

    def __init__(
        self,
        fetch: FetchJwks,
        *,
        ttl_s: float = 600.0,
        min_refresh_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._ttl_s = ttl_s
        self._min_refresh_s = min_refresh_s
        self._clock = clock
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()

    async def _refresh(self) -> None:
        data = await self._fetch()
        keys: dict[str, PyJWK] = {}
        for jwk in data.get("keys", []):
            kid = jwk.get("kid")
            if not kid:
                continue
            try:
                keys[kid] = PyJWK.from_dict(jwk)
            except jwt.PyJWTError:
                log.warning("jwks_key_skipped", kid=kid)
        self._keys = keys
        self._fetched_at = self._clock()
        log.info("jwks_refreshed", kids=sorted(keys))

    def _age(self) -> float:
        return float("inf") if self._fetched_at is None else self._clock() - self._fetched_at

    async def get(self, kid: str) -> PyJWK:
        if self._age() > self._ttl_s or (
            kid not in self._keys and self._age() > self._min_refresh_s
        ):
            async with self._lock:
                # Re-check: another request may have refreshed while we waited.
                stale = self._age() > self._ttl_s
                unknown = kid not in self._keys and self._age() > self._min_refresh_s
                if stale or unknown:
                    try:
                        await self._refresh()
                    except (httpx2.HTTPError, ValueError) as exc:
                        # Keep serving known keys if the JWKS endpoint blips.
                        log.warning("jwks_refresh_failed", error=type(exc).__name__)
                        if not self._keys:
                            raise TokenError("signing keys unavailable") from exc
        key = self._keys.get(kid)
        if key is None:
            raise TokenError("unknown signing key")
        return key


async def verify_token(token: str, jwks: JwksCache, *, issuer: str, audience: str) -> Claims:
    """Return the token's claims, or raise TokenError. Checks signature, exp, iss, aud, sub."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError("malformed token") from exc
    if header.get("alg") not in ALGORITHMS:
        raise TokenError("unsupported algorithm")
    kid = header.get("kid")
    if not isinstance(kid, str):
        raise TokenError("token has no key id")

    key = await jwks.get(kid)
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key=key,
            algorithms=ALGORITHMS,
            audience=audience,
            issuer=issuer,
            leeway=LEEWAY_S,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc

    def text(name: str) -> str | None:
        value = payload.get(name)
        return value if isinstance(value, str) and value else None

    return Claims(
        sub=str(payload["sub"]),
        email=text("email"),
        name=text("name"),
        login=text("login"),
        image=text("image"),
        raw=payload,
    )
