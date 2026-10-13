"""Profiles: idempotent creation from sign-in data, lookups and updates."""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import Role
from devgrill.infra.models import Entitlement, Profile, Streak

_HANDLE_MAX = 39  # GitHub's limit, and our check constraint's
_INVALID = re.compile(r"[^A-Za-z0-9-]+")


@dataclass(frozen=True, slots=True)
class Identity:
    """What the auth layer knows about a user at sign-in."""

    user_id: uuid.UUID
    login: str | None = None
    name: str | None = None
    email: str | None = None
    image: str | None = None


def handle_candidate(identity: Identity) -> str:
    """A valid handle from the GitHub login, else the name or email, else "player"."""
    for source in (identity.login, identity.name, (identity.email or "").split("@")[0]):
        if source:
            cleaned = _INVALID.sub("-", source).strip("-")[:_HANDLE_MAX].strip("-")
            if cleaned:
                return cleaned
    return "player"


async def get(session: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    return await session.get(Profile, user_id)


async def get_by_handle(session: AsyncSession, handle: str) -> Profile | None:
    result = await session.execute(select(Profile).where(Profile.handle == handle))
    return result.scalar_one_or_none()


async def ensure(
    session: AsyncSession, identity: Identity, *, admin_logins: frozenset[str] = frozenset()
) -> tuple[Profile, bool]:
    """Return the user's profile, creating it (and its defaults) if needed.

    Safe to call concurrently: inserts use ON CONFLICT DO NOTHING, and a handle collision
    retries with a suffix. Returns (profile, created).
    """
    existing = await get(session, identity.user_id)
    if existing is not None:
        await _grant_configured_admin(session, existing, identity, admin_logins)
        return existing, False

    base = handle_candidate(identity)
    roles = [Role.USER.value]
    if identity.login and identity.login.lower() in admin_logins:
        roles.append(Role.ADMIN.value)

    for attempt in range(8):
        if attempt == 0:
            handle = base
        else:
            suffix = f"-{secrets.token_hex(2)}"
            handle = base[: _HANDLE_MAX - len(suffix)] + suffix
        inserted = await session.execute(
            insert(Profile)
            .values(
                user_id=identity.user_id,
                handle=handle,
                display_name=identity.name or identity.login or handle,
                avatar_url=identity.image,
                roles=roles,
            )
            .on_conflict_do_nothing()
            .returning(Profile.user_id)
        )
        if inserted.scalar_one_or_none() is not None:
            break
        # Either another request created this user's profile, or the handle is taken.
        if await get(session, identity.user_id) is not None:
            break
    else:
        raise RuntimeError("could not allocate a unique handle")

    await session.execute(
        insert(Entitlement).values(user_id=identity.user_id).on_conflict_do_nothing()
    )
    await session.execute(insert(Streak).values(user_id=identity.user_id).on_conflict_do_nothing())
    await session.flush()
    profile = await get(session, identity.user_id)
    assert profile is not None
    await session.refresh(profile)
    return profile, True


async def _grant_configured_admin(
    session: AsyncSession, profile: Profile, identity: Identity, admin_logins: frozenset[str]
) -> None:
    if (
        identity.login
        and identity.login.lower() in admin_logins
        and Role.ADMIN.value not in profile.roles
    ):
        profile.roles = [*profile.roles, Role.ADMIN.value]
        await session.flush()


def merged_prefs(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge preference updates; `None` removes a key."""
    merged = dict(current)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged
