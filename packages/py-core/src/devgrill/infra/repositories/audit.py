"""The audit log: every admin and content action, who did it and to what (phase 7 gate)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.infra.models import AuditLog, Profile


async def record(
    session: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    target: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Add an entry in the caller's transaction: the action and its record commit together."""
    session.add(AuditLog(actor_id=actor_id, action=action, target=target, data=data or {}))
    await session.flush()


async def recent(
    session: AsyncSession, *, limit: int, before_id: int | None = None
) -> list[tuple[AuditLog, str | None]]:
    """Newest first, with the actor's handle."""
    stmt = (
        select(AuditLog, Profile.handle)
        .outerjoin(Profile, Profile.user_id == AuditLog.actor_id)
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(AuditLog.id < before_id)
    return [(entry, handle) for entry, handle in (await session.execute(stmt)).all()]
