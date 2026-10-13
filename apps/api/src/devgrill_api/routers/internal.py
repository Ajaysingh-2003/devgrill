"""Server-to-server endpoints for the web app, authenticated by HMAC (not user tokens).

Excluded from the public OpenAPI schema; the web app calls them from Better Auth hooks.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from devgrill.infra.repositories import profiles
from devgrill_api.auth import internal
from devgrill_api.deps import SessionDep, SettingsDep
from devgrill_api.errors import AppError
from devgrill_api.schemas import ProfileHookIn, ProfileHookOut

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


async def verified_body(
    request: Request,
    settings: SettingsDep,
    x_devgrill_timestamp: Annotated[str | None, Header()] = None,
    x_devgrill_signature: Annotated[str | None, Header()] = None,
) -> bytes:
    body = await request.body()
    try:
        internal.verify(
            settings.internal_hmac_secret, x_devgrill_timestamp, x_devgrill_signature, body
        )
    except internal.SignatureError as exc:
        raise AppError(401, "invalid_signature", str(exc)) from exc
    return body


@router.post("/profiles", response_model=ProfileHookOut)
async def upsert_profile(
    body: Annotated[bytes, Depends(verified_body)], session: SessionDep, settings: SettingsDep
) -> ProfileHookOut:
    """Create the profile for a new user (idempotent; also applies configured admin roles)."""
    data = ProfileHookIn.model_validate_json(body)
    profile, created = await profiles.ensure(
        session,
        profiles.Identity(
            user_id=data.user_id,
            login=data.login,
            name=data.name,
            email=data.email,
            image=str(data.image) if data.image else None,
        ),
        admin_logins=settings.admin_logins,
    )
    return ProfileHookOut(user_id=profile.user_id, handle=profile.handle, created=created)
