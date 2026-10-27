"""Profiles and entitlements (docs/PLAN.md §9.2, identity and profile)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from devgrill.domain.enums import ExperienceLevel, Plan
from devgrill.infra.db import Base
from devgrill.infra.models._types import (
    CreatedAt,
    JsonObject,
    Timestamp,
    UpdatedAt,
    pg_enum,
    user_fk,
)


class Profile(Base):
    """One per signed-in user. `user_id` is Better Auth's user id (auth schema).

    There is deliberately no foreign key to `auth.user`: the two schemas migrate
    independently (ADR 011). The sign-in hook (POST /internal/profiles) and the API's first
    authenticated request both create the row idempotently; every other app table that
    refers to a user points here.
    """

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("handle ~ '^[A-Za-z0-9][A-Za-z0-9-]{0,38}$'", name="handle_format"),
        CheckConstraint(
            "roles <@ ARRAY['user','author','reviewer','admin']::text[]", name="roles_known"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    handle: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        pg_enum(ExperienceLevel, "experience_level")
    )
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("ARRAY['user']::text[]")
    )
    prefs: Mapped[JsonObject]
    #: Opt-in (phase 7): a new profile is visible only to its owner until they share it.
    is_public: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class Entitlement(Base):
    """Plan limits per user. Everyone is on the free defaults until billing (phase 9)."""

    __tablename__ = "entitlements"

    user_id: Mapped[uuid.UUID] = mapped_column(user_fk(), primary_key=True)
    plan: Mapped[Plan] = mapped_column(pg_enum(Plan, "plan"), server_default=Plan.FREE.value)
    limits: Mapped[JsonObject]
    valid_until: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]
