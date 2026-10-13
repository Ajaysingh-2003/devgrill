"""JWT verification and JWKS rotation (phase 2 gate: expired, tampered, wrong audience,
rotation)."""

from __future__ import annotations

import base64
import json
import time
import uuid

import jwt
import pytest

from devgrill_api.auth import guest, internal
from devgrill_api.auth.jwks import JwksCache, TokenError, verify_token

ISS, AUD = "http://localhost:3000", "devgrill-api"


def b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def cache(signer, **kwargs) -> JwksCache:  # type: ignore[no-untyped-def]
    return JwksCache(signer.fetch, **{"ttl_s": 600, "min_refresh_s": 0, **kwargs})


async def check(token: str, jwks: JwksCache, *, aud: str = AUD, iss: str = ISS):  # type: ignore[no-untyped-def]
    return await verify_token(token, jwks, issuer=iss, audience=aud)


async def test_valid_token_yields_claims(signer) -> None:  # type: ignore[no-untyped-def]
    sub = uuid.uuid4()
    claims = await check(signer.token(sub, login="ajay", name="Ajay"), cache(signer))
    assert claims.sub == str(sub)
    assert claims.login == "ajay"


async def test_expired_token_is_rejected(signer) -> None:  # type: ignore[no-untyped-def]
    # Beyond the 30 s clock-skew allowance.
    with pytest.raises(TokenError, match="expired"):
        await check(signer.token(exp_in=-60), cache(signer))


async def test_tampered_payload_is_rejected(signer) -> None:  # type: ignore[no-untyped-def]
    header, _, signature = signer.token().split(".")
    claims = jwt.decode(signer.token(), options={"verify_signature": False})
    claims["sub"] = str(uuid.uuid4())
    with pytest.raises(TokenError, match="invalid"):
        await check(f"{header}.{b64(claims)}.{signature}", cache(signer))


async def test_wrong_audience_and_issuer_are_rejected(signer) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TokenError):
        await check(signer.token(aud="someone-else"), cache(signer))
    with pytest.raises(TokenError):
        await check(signer.token(iss="https://evil.example"), cache(signer))


async def test_algorithm_confusion_is_rejected(signer) -> None:  # type: ignore[no-untyped-def]
    kid = signer.published[-1]
    now = int(time.time())
    claims = {"sub": "x", "iss": ISS, "aud": AUD, "iat": now, "exp": now + 60}
    hs256 = jwt.encode(claims, "g" * 32, algorithm="HS256", headers={"kid": kid})
    unsigned = jwt.encode(claims, None, algorithm="none", headers={"kid": kid})  # type: ignore[arg-type]
    for token in (hs256, unsigned):
        with pytest.raises(TokenError, match="algorithm"):
            await check(token, cache(signer))


async def test_garbage_is_rejected(signer) -> None:  # type: ignore[no-untyped-def]
    for token in ("", "not.a.jwt", "a.b"):
        with pytest.raises(TokenError):
            await check(token, cache(signer))


async def test_key_rotation_is_picked_up_on_first_unknown_kid(signer) -> None:  # type: ignore[no-untyped-def]
    jwks = cache(signer, min_refresh_s=0)
    await check(signer.token(), jwks)
    assert signer.fetches == 1

    new_kid = signer.rotate()
    # Old tokens keep working during the grace period; new ones trigger one refetch.
    await check(signer.token(kid=signer.published[0]), jwks)
    assert signer.fetches == 1
    await check(signer.token(kid=new_kid), jwks)
    assert signer.fetches == 2

    # Once the old key is retired from the JWKS, its tokens stop verifying after a refresh.
    signer.published.remove(signer.published[0])
    stale_kid = next(k for k in signer.keys if k not in signer.published)
    jwks_after = cache(signer)
    with pytest.raises(TokenError, match="unknown signing key"):
        await check(signer.token(kid=stale_kid), jwks_after)


async def test_unknown_kids_cannot_force_repeated_fetches(signer) -> None:  # type: ignore[no-untyped-def]
    clock = [0.0]
    jwks = JwksCache(signer.fetch, ttl_s=600, min_refresh_s=30, clock=lambda: clock[0])
    await check(signer.token(), jwks)
    for _ in range(5):
        clock[0] += 1
        _, payload, signature = signer.token().split(".")
        header = b64({"alg": "EdDSA", "kid": uuid.uuid4().hex})
        with pytest.raises(TokenError):
            await check(f"{header}.{payload}.{signature}", jwks)
    assert signer.fetches == 1


async def test_jwks_outage_keeps_serving_known_keys(signer) -> None:  # type: ignore[no-untyped-def]
    import httpx2

    calls = {"n": 0}

    async def flaky():  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] > 1:
            raise httpx2.ConnectError("down")
        return signer.jwks()

    clock = [0.0]
    jwks = JwksCache(flaky, ttl_s=10, min_refresh_s=0, clock=lambda: clock[0])
    await check(signer.token(), jwks)
    clock[0] = 100  # past the TTL: refresh fails, cached key still verifies
    await check(signer.token(), jwks)
    assert calls["n"] == 2


# ---------------------------------------------------------------------- guest tokens


def test_guest_tokens_round_trip_and_reject_tampering() -> None:
    from datetime import timedelta

    issued = guest.issue("s" * 40, timedelta(days=1))
    assert guest.verify(issued.token, "s" * 40) == issued.jti
    with pytest.raises(guest.GuestTokenError):
        guest.verify(issued.token, "t" * 40)
    expired = guest.issue("s" * 40, timedelta(seconds=-10))
    with pytest.raises(guest.GuestTokenError):
        guest.verify(expired.token, "s" * 40)
    assert guest.guest_hash(issued.jti) != issued.jti


def test_user_tokens_are_not_guest_tokens(signer) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(guest.GuestTokenError):
        guest.verify(signer.token(), "s" * 40)


# ------------------------------------------------------------------ internal HMAC


def test_internal_signatures() -> None:
    secret, body, now = "k" * 40, b'{"a":1}', 1_800_000_000
    sig = internal.sign(secret, now, body)
    internal.verify(secret, str(now), sig, body, now=now)
    with pytest.raises(internal.SignatureError, match="bad signature"):
        internal.verify(secret, str(now), sig, b'{"a":2}', now=now)
    with pytest.raises(internal.SignatureError, match="stale"):
        internal.verify(secret, str(now), sig, body, now=now + 301)
    with pytest.raises(internal.SignatureError, match="missing"):
        internal.verify(secret, None, sig, body, now=now)
    with pytest.raises(internal.SignatureError, match="not configured"):
        internal.verify("", str(now), sig, body, now=now)
