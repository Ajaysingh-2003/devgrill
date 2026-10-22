"""Catalog and content (docs/PLAN.md §9.2): tracks, scenarios and everything a version pins."""

from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Float,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from devgrill.domain.enums import (
    Access,
    ApproachOutcome,
    Difficulty,
    FaultKind,
    ProbeKind,
    QuickfireKind,
    ScenarioSource,
    ScenarioStatus,
    TrackStatus,
)
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

#: OpenAI text-embedding-3-small dimensions (approach clustering, phase 6).
EMBEDDING_DIMENSIONS = 1536


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[UuidPk]
    slug: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[TrackStatus] = mapped_column(
        pg_enum(TrackStatus, "track_status"), server_default=TrackStatus.PUBLISHED.value
    )
    created_at: Mapped[CreatedAt]


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("track_id", "slug", name="uq_topics_track_id_slug"),)

    id: Mapped[UuidPk]
    track_id: Mapped[uuid.UUID] = mapped_column(fk("tracks.id"))
    slug: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    primer_md: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)


class BaseApp(Base):
    """A runnable system scenarios break (e.g. ShopKart). Built by the content CLI."""

    __tablename__ = "base_apps"

    id: Mapped[UuidPk]
    slug: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    services: Mapped[JsonObject]
    image_digests: Mapped[JsonObject]
    created_at: Mapped[CreatedAt]


class Fault(Base):
    __tablename__ = "faults"

    id: Mapped[UuidPk]
    slug: Mapped[str] = mapped_column(Text, unique=True)
    kind: Mapped[FaultKind] = mapped_column(pg_enum(FaultKind, "fault_kind"))
    params_schema: Mapped[JsonObject]
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint("est_minutes BETWEEN 1 AND 240", name="est_minutes_range"),
        # Library queries filter on track, status and difficulty together.
        Index("ix_scenarios_track_id_status_difficulty", "track_id", "status", "difficulty"),
        Index("ix_scenarios_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[UuidPk]
    slug: Mapped[str] = mapped_column(Text, unique=True)
    track_id: Mapped[uuid.UUID] = mapped_column(fk("tracks.id", ondelete="RESTRICT"))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("topics.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(pg_enum(Difficulty, "difficulty"))
    est_minutes: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[ScenarioStatus] = mapped_column(
        pg_enum(ScenarioStatus, "scenario_status"), server_default=ScenarioStatus.DRAFT.value
    )
    source: Mapped[ScenarioSource] = mapped_column(
        pg_enum(ScenarioSource, "scenario_source"),
        server_default=ScenarioSource.HANDWRITTEN.value,
    )
    #: Which plans may play it live (ADR 013). Mirrors the current version's spec.
    access: Mapped[Access] = mapped_column(
        pg_enum(Access, "access"), server_default=Access.PRO.value
    )
    # Circular with scenario_versions.scenario_id, so the constraint is added after both tables.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("scenario_versions.id", ondelete="SET NULL", use_alter=True), index=True
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    rating: Mapped[GlickoRating]
    rd: Mapped[GlickoRd]
    vol: Mapped[GlickoVol]
    created_by: Mapped[uuid.UUID | None] = mapped_column(user_fk(ondelete="SET NULL"), index=True)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ScenarioVersion(Base):
    """Immutable once published; attempts pin the version they played."""

    __tablename__ = "scenario_versions"
    __table_args__ = (
        UniqueConstraint("scenario_id", "version", name="uq_scenario_versions_scenario_id_version"),
    )

    id: Mapped[UuidPk]
    scenario_id: Mapped[uuid.UUID] = mapped_column(fk("scenarios.id"))
    version: Mapped[int] = mapped_column(Integer)
    spec: Mapped[JsonObject]
    content_hash: Mapped[str] = mapped_column(Text)
    base_app_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("base_apps.id", ondelete="RESTRICT"), index=True
    )
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    solver_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    published_at: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]


class ScenarioFault(Base):
    __tablename__ = "scenario_faults"

    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        fk("scenario_versions.id"), primary_key=True
    )
    fault_id: Mapped[uuid.UUID] = mapped_column(
        fk("faults.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    params: Mapped[JsonObject]


class Probe(Base):
    __tablename__ = "probes"
    __table_args__ = (
        UniqueConstraint("scenario_version_id", "key", name="uq_probes_scenario_version_id_key"),
        CheckConstraint("weight > 0", name="weight_positive"),
    )

    id: Mapped[UuidPk]
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(fk("scenario_versions.id"))
    key: Mapped[str] = mapped_column(Text)
    kind: Mapped[ProbeKind] = mapped_column(pg_enum(ProbeKind, "probe_kind"))
    config: Mapped[JsonObject]
    target: Mapped[JsonObject]
    weight: Mapped[float] = mapped_column(Float, server_default=text("1"))


class Hint(Base):
    __tablename__ = "hints"
    __table_args__ = (CheckConstraint("tier BETWEEN 1 AND 3", name="tier_range"),)

    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        fk("scenario_versions.id"), primary_key=True
    )
    tier: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    body_md: Mapped[str] = mapped_column(Text)


class Rubric(Base):
    """Postmortem grading criteria: `[{key, max, description, anchors}]`."""

    __tablename__ = "rubrics"

    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        fk("scenario_versions.id"), primary_key=True
    )
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )


class Approach(Base):
    """A known way to fix a scenario. Grows from classification and review (phase 6)."""

    __tablename__ = "approaches"
    __table_args__ = (
        UniqueConstraint("scenario_id", "key", name="uq_approaches_scenario_id_key"),
        Index(
            "ix_approaches_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UuidPk]
    scenario_id: Mapped[uuid.UUID] = mapped_column(fk("scenarios.id"))
    key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    outcome: Mapped[ApproachOutcome] = mapped_column(pg_enum(ApproachOutcome, "approach_outcome"))
    idea_md: Mapped[str] = mapped_column(Text)
    exemplar_patch: Mapped[str | None] = mapped_column(Text)
    pros: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    cons: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # Circular with attempts.approach_id.
    discovered_from_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("attempts.id", ondelete="SET NULL", use_alter=True), index=True
    )
    created_at: Mapped[CreatedAt]


class ApproachCandidate(Base):
    """A fix the classifier didn't recognise (phase 6): the admin queue groups similar ones,
    and an admin promotes a group to a known approach or dismisses it."""

    __tablename__ = "approach_candidates"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'promoted', 'dismissed')", name="status_known"),
    )

    id: Mapped[UuidPk]
    scenario_id: Mapped[uuid.UUID] = mapped_column(fk("scenarios.id"), index=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"), unique=True)
    #: The classifier's description of the change (no player text).
    summary: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    status: Mapped[str] = mapped_column(Text, server_default=text("'open'"))
    approach_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("approaches.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[CreatedAt]


class QuickfireCard(Base):
    __tablename__ = "quickfire_cards"

    id: Mapped[UuidPk]
    track_id: Mapped[uuid.UUID] = mapped_column(fk("tracks.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[QuickfireKind] = mapped_column(pg_enum(QuickfireKind, "quickfire_kind"))
    prompt: Mapped[JsonObject]
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    answer: Mapped[str] = mapped_column(Text)
    explanation_md: Mapped[str] = mapped_column(Text)
    rating: Mapped[GlickoRating]
    rd: Mapped[GlickoRd]
    vol: Mapped[GlickoVol]
    created_at: Mapped[CreatedAt]
