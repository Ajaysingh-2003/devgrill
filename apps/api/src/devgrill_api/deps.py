"""Request-scoped dependencies: the unit of work, settings, and who is calling."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any

import structlog
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.config import Settings
from devgrill.domain.enums import Role
from devgrill.infra.models import Profile
from devgrill.infra.repositories import profiles
from devgrill_api.auth import guest
from devgrill_api.auth.jwks import JwksCache, TokenError, verify_token
from devgrill_api.errors import AppError

log = structlog.get_logger(__name__)

_UNAUTHORIZED = {"WWW-Authenticate": 'Bearer realm="devgrill"'}


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request: committed when the handler returns, rolled back on error.

    Declared with scope="function", so the commit happens before the response is sent:
    a failed commit becomes a 500, never a 200 for data that wasn't saved.
    """
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    profile: Profile

    @property
    def roles(self) -> frozenset[str]:
        return frozenset(self.profile.roles)

    def has_role(self, role: Role) -> bool:
        return role.value in self.roles


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AppError(401, "invalid_token", "Use the Bearer scheme.", headers=_UNAUTHORIZED)
    return token.strip()


async def _user_from_token(
    request: Request, session: AsyncSession, settings: Settings, token: str
) -> CurrentUser:
    jwks: JwksCache = request.app.state.jwks
    try:
        claims = await verify_token(
            token, jwks, issuer=settings.auth_issuer, audience=settings.auth_audience
        )
        user_id = uuid.UUID(claims.sub)
    except (TokenError, ValueError) as exc:
        detail = str(exc) if isinstance(exc, TokenError) else "invalid subject"
        raise AppError(401, "invalid_token", detail, headers=_UNAUTHORIZED) from exc

    profile = await profiles.get(session, user_id)
    if profile is None:
        # Created in its own transaction: a route that then fails (403, 422...) rolls back
        # the request's transaction, and must not take the new profile with it.
        async with request.app.state.session_factory() as own, own.begin():
            _, created = await profiles.ensure(
                own,
                profiles.Identity(
                    user_id=user_id,
                    login=claims.login,
                    name=claims.name,
                    email=claims.email,
                    image=claims.image,
                ),
                admin_logins=settings.admin_logins,
            )
        if created:
            log.info("profile_created_lazily", user_id=str(user_id))
        profile = await profiles.get(session, user_id)
        if profile is None:  # pragma: no cover - committed above
            raise AppError(500, "profile_unavailable", "Could not load your profile.")
    structlog.contextvars.bind_contextvars(user_id=str(user_id))
    return CurrentUser(id=user_id, profile=profile)


async def optional_user(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser | None:
    """The signed-in user, or None for anonymous calls. A bad token is still a 401."""
    token = _bearer(authorization)
    if token is None:
        return None
    return await _user_from_token(request, session, settings, token)


async def current_user(user: Annotated[CurrentUser | None, Depends(optional_user)]) -> CurrentUser:
    if user is None:
        raise AppError(401, "unauthenticated", "Sign in to continue.", headers=_UNAUTHORIZED)
    return user


OptionalUser = Annotated[CurrentUser | None, Depends(optional_user)]
User = Annotated[CurrentUser, Depends(current_user)]


def require_role(*roles: Role) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    """403 unless the user has at least one of `roles` (admin implies every role)."""
    allowed = {r.value for r in roles} | {Role.ADMIN.value}

    async def check(user: User) -> CurrentUser:
        if not allowed & user.roles:
            raise AppError(403, "forbidden", "You don't have access to this.")
        return user

    return check


Admin = Annotated[CurrentUser, Depends(require_role(Role.ADMIN))]


async def guest_jti(
    settings: SettingsDep,
    x_guest_token: Annotated[str | None, Header()] = None,
) -> str | None:
    """The calling guest's token id (from the X-Guest-Token header), if any."""
    if not x_guest_token:
        return None
    try:
        return guest.verify(x_guest_token, settings.guest_token_secret)
    except guest.GuestTokenError as exc:
        raise AppError(401, "invalid_guest_token", str(exc)) from exc


GuestJti = Annotated[str | None, Depends(guest_jti)]


def guest_ttl(settings: Settings) -> timedelta:
    return timedelta(days=settings.guest_token_ttl_days)
