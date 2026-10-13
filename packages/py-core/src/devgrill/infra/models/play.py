"""Play (docs/PLAN.md §9.2): attempts and everything recorded while one runs."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    Identity,
    Index,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from devgrill.domain.attempt import LIVE_STATES
from devgrill.domain.enums import AttemptMode, AttemptState, AuthorKind, SandboxDriver, VerifyStatus
from devgrill.infra.db import Base
from devgrill.infra.models._types import (
    CreatedAt,
    JsonObject,
    Timestamp,
    UpdatedAt,
    UuidPk,
    fk,
    pg_enum,
    user_fk,
)

_LIVE = ", ".join(f"'{s.value}'" for s in sorted(LIVE_STATES))


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        # Guests play before signing up; their attempts are claimed by user id later.
        CheckConstraint(
            "user_id IS NOT NULL OR guest_token_hash IS NOT NULL", name="owner_present"
        ),
        CheckConstraint("hints_used >= 0", name="hints_used_non_negative"),
        Index("ix_attempts_user_id_started_at", "user_id", text("started_at DESC")),
        # One live attempt per user (a sandbox each): docs/PLAN.md §9.3.
        Index(
            "uq_attempts_user_id_live",
            "user_id",
            unique=True,
            postgresql_where=text(f"state IN ({_LIVE})"),
        ),
        Index(
            "ix_attempts_guest_token_hash",
            "guest_token_hash",
            postgresql_where=text("guest_token_hash IS NOT NULL"),
        ),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[uuid.UUID | None] = mapped_column(user_fk())
    guest_token_hash: Mapped[str | None] = mapped_column(Text)
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        fk("scenario_versions.id", ondelete="RESTRICT"), index=True
    )
    mode: Mapped[AttemptMode] = mapped_column(pg_enum(AttemptMode, "attempt_mode"))
    state: Mapped[AttemptState] = mapped_column(
        pg_enum(AttemptState, "attempt_state"), server_default=AttemptState.PROVISIONING.value
    )
    started_at: Mapped[CreatedAt]
    active_at: Mapped[Timestamp | None]
    mitigated_at: Mapped[Timestamp | None]
    resolved_at: Mapped[Timestamp | None]
    ended_at: Mapped[Timestamp | None]
    hints_used: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    score: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rating_delta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approach_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("approaches.id", ondelete="SET NULL"), index=True
    )
    approach_confidence: Mapped[float | None] = mapped_column(Float)
    workflow_id: Mapped[str | None] = mapped_column(Text)


class SandboxSession(Base):
    """Where an attempt runs. Cost is tracked from day one."""

    __tablename__ = "sandbox_sessions"

    id: Mapped[UuidPk]
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"), index=True)
    driver: Mapped[SandboxDriver] = mapped_column(pg_enum(SandboxDriver, "sandbox_driver"))
    host: Mapped[str | None] = mapped_column(Text)
    external_ref: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    resources: Mapped[JsonObject]
    created_at: Mapped[CreatedAt]
    ready_at: Mapped[Timestamp | None]
    expires_at: Mapped[Timestamp | None]
    destroyed_at: Mapped[Timestamp | None]
    cpu_seconds: Mapped[float | None] = mapped_column(Float)
    est_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class AttemptEvent(Base):
    """The investigation trail. High volume: bigint identity key, partitioned in phase 8."""

    __tablename__ = "attempt_events"
    __table_args__ = (Index("ix_attempt_events_attempt_id_ts", "attempt_id", "ts"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"))
    ts: Mapped[CreatedAt]
    type: Mapped[str] = mapped_column(Text)
    payload: Mapped[JsonObject]


class Recording(Base):
    """Terminal casts and code diffs stored in object storage."""

    __tablename__ = "recordings"

    id: Mapped[UuidPk]
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[CreatedAt]


class CodeChange(Base):
    __tablename__ = "code_changes"

    id: Mapped[UuidPk]
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"), index=True)
    diff: Mapped[str] = mapped_column(Text)
    files: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    created_at: Mapped[CreatedAt]
    deployed_at: Mapped[Timestamp | None]
    deploy_ok: Mapped[bool | None]


class WarRoomMessage(Base):
    __tablename__ = "war_room_messages"
    __table_args__ = (Index("ix_war_room_messages_attempt_id_ts", "attempt_id", "ts"),)

    id: Mapped[UuidPk]
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"))
    author_kind: Mapped[AuthorKind] = mapped_column(pg_enum(AuthorKind, "author_kind"))
    persona_key: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    ts: Mapped[CreatedAt]
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("llm_calls.id", ondelete="SET NULL"), index=True
    )


class VerifyRun(Base):
    __tablename__ = "verify_runs"

    id: Mapped[UuidPk]
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"), index=True)
    code_change_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("code_changes.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[VerifyStatus] = mapped_column(
        pg_enum(VerifyStatus, "verify_status"), server_default=VerifyStatus.QUEUED.value
    )
    started_at: Mapped[Timestamp | None]
    finished_at: Mapped[Timestamp | None]
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[CreatedAt]


class ProbeResult(Base):
    __tablename__ = "probe_results"

    verify_run_id: Mapped[uuid.UUID] = mapped_column(fk("verify_runs.id"), primary_key=True)
    probe_id: Mapped[uuid.UUID] = mapped_column(
        fk("probes.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    passed: Mapped[bool]
    observed: Mapped[JsonObject]
    artifact_key: Mapped[str | None] = mapped_column(Text)


class Postmortem(Base):
    __tablename__ = "postmortems"

    id: Mapped[UuidPk]
    attempt_id: Mapped[uuid.UUID] = mapped_column(fk("attempts.id"), unique=True)
    body_md: Mapped[str] = mapped_column(Text, server_default=text("''"))
    submitted_at: Mapped[Timestamp | None]
    is_public: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class PostmortemGrade(Base):
    """One grader's verdict. Several graders per postmortem are allowed (calibration)."""

    __tablename__ = "postmortem_grades"

    id: Mapped[UuidPk]
    postmortem_id: Mapped[uuid.UUID] = mapped_column(fk("postmortems.id"), index=True)
    judge_model: Mapped[str] = mapped_column(Text)
    judge_prompt_version: Mapped[str] = mapped_column(Text)
    scores: Mapped[JsonObject]
    total: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    feedback_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[CreatedAt]
