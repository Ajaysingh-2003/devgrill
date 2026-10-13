"""Guest tokens: let people play `/try` before signing up, then claim the attempts.

A guest token is an HS256 JWT signed with GUEST_TOKEN_SECRET (never the user-token keys) and
an audience of its own, so it can't be passed off as a user token or vice versa. The web app
keeps it in an httpOnly cookie and forwards it as `X-Guest-Token`. Attempts store only a
hash of its `jti`, so a database leak doesn't hand out playable guest sessions.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

GUEST_AUDIENCE = "devgrill-guest"
GUEST_ISSUER = "devgrill-api"
_ALGORITHM = "HS256"


class GuestTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GuestToken:
    token: str
    jti: str
    expires_at: datetime


def guest_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode()).hexdigest()


def issue(secret: str, ttl: timedelta, *, now: datetime | None = None) -> GuestToken:
    if not secret:
        raise GuestTokenError("guest tokens are not configured")
    issued = now or datetime.now(UTC)
    expires = issued + ttl
    jti = secrets.token_urlsafe(24)
    token = jwt.encode(
        {
            "iss": GUEST_ISSUER,
            "aud": GUEST_AUDIENCE,
            "jti": jti,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
        },
        secret,
        algorithm=_ALGORITHM,
    )
    return GuestToken(token=token, jti=jti, expires_at=expires)


def verify(token: str, secret: str) -> str:
    """Return the token's `jti` or raise GuestTokenError."""
    if not secret:
        raise GuestTokenError("guest tokens are not configured")
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            audience=GUEST_AUDIENCE,
            issuer=GUEST_ISSUER,
            options={"require": ["exp", "jti", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise GuestTokenError("invalid guest token") from exc
    jti = payload["jti"]
    if not isinstance(jti, str) or not jti:
        raise GuestTokenError("invalid guest token")
    return jti
