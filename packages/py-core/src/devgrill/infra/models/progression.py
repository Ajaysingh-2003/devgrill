"""Progression and social (docs/PLAN.md §9.2): ratings, streaks, challenges, cohorts."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from devgrill.domain.enums import ChallengeKind, CohortRole, StreakMode
from devgrill.infra.db import Base
from devgrill.infra.models._types import (
    CreatedAt,
    GlickoRating,
    GlickoRd,
    GlickoVol,
    JsonObject,
    Timestamp,
    UpdatedAt,
    UuidPk,
    fk,
    pg_enum,
    user_fk,
)


class SkillRating(Base):
    """Glicko-2 per user and track. Quick Fire uses its own pseudo-track."""

    __tablename__ = "skill_ratings"

    user_id: Mapped[uuid.UUID] = mapped_column(user_fk(), primary_key=True)
    track_id: Mapped[uuid.UUID] = mapped_column(fk("tracks.id"), primary_key=True, index=True)
    rating: Mapped[GlickoRating]
    rd: Mapped[GlickoRd]
    vol: Mapped[GlickoVol]
    games: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[UpdatedAt]


class RatingHistory(Base):
    """Every rating change, with `{rating, rd, vol}` before and after."""

    __tablename__ = "rating_history"
    __table_args__ = (Index("ix_rating_history_user_id_track_id_ts", "user_id", "track_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(user_fk())
    track_id: Mapped[uuid.UUID] = mapped_column(fk("tracks.id"), index=True)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("attempts.id", ondelete="SET NULL"), index=True
    )
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    ts: Mapped[CreatedAt]


class ActivityDay(Base):
    """Source of truth for streaks: one row per user per local day with activity."""

    __tablename__ = "activity_days"

    user_id: Mapped[uuid.UUID] = mapped_column(user_fk(), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kinds: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))


class Streak(Base):
    """Derived from activity_days (devgrill.domain.streaks) and recomputable at any time."""

    __tablename__ = "streaks"
    __table_args__ = (CheckConstraint("freezes >= 0", name="freezes_non_negative"),)

    user_id: Mapped[uuid.UUID] = mapped_column(user_fk(), primary_key=True)
    mode: Mapped[StreakMode] = mapped_column(
        pg_enum(StreakMode, "streak_mode"), server_default=StreakMode.DAILY.value
    )
    current: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    longest: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    freezes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_day: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[UpdatedAt]


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (
        UniqueConstraint("kind", "starts_at", name="uq_challenges_kind_starts_at"),
        CheckConstraint("ends_at > starts_at", name="window_valid"),
    )

    id: Mapped[UuidPk]
    kind: Mapped[ChallengeKind] = mapped_column(pg_enum(ChallengeKind, "challenge_kind"))
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        fk("scenario_versions.id", ondelete="RESTRICT"), index=True
    )
    starts_at: Mapped[Timestamp]
    ends_at: Mapped[Timestamp]


class ChallengeEntry(Base):
    __tablename__ = "challenge_entries"

    challenge_id: Mapped[uuid.UUID] = mapped_column(fk("challenges.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(user_fk(), primary_key=True, index=True)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("attempts.id", ondelete="SET NULL"), index=True
    )
    result: Mapped[JsonObject]
    created_at: Mapped[CreatedAt]


class Cohort(Base):
    """A private league joined with an invite code."""

    __tablename__ = "cohorts"

    id: Mapped[UuidPk]
    name: Mapped[str] = mapped_column(Text)
    invite_code: Mapped[str] = mapped_column(Text, unique=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(user_fk(), index=True)
    created_at: Mapped[CreatedAt]


class CohortMember(Base):
    __tablename__ = "cohort_members"

    cohort_id: Mapped[uuid.UUID] = mapped_column(fk("cohorts.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(user_fk(), primary_key=True, index=True)
    role: Mapped[CohortRole] = mapped_column(
        pg_enum(CohortRole, "cohort_role"), server_default=CohortRole.MEMBER.value
    )
    joined_at: Mapped[CreatedAt]
