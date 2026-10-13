"""Platform and operations (docs/PLAN.md §9.2).

Idempotency keys live in Valkey (24 h TTL), not in a table: they are short-lived and
looked up on every retried POST.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Identity, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from devgrill.infra.db import Base
from devgrill.infra.models._types import (
    CreatedAt,
    JsonObject,
    UpdatedAt,
    UuidPk,
    fk,
    user_fk,
)


class LlmCall(Base):
    """One model call: budget enforcement and cost dashboards (phase 6)."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_created_at", "created_at"),
        Index("ix_llm_calls_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[UuidPk]
    feature: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cached_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default=text("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("attempts.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(user_fk(ondelete="SET NULL"))
    trace_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[CreatedAt]


class GenerationJob(Base):
    """AI scenario generation (phase 10)."""

    __tablename__ = "generation_jobs"

    id: Mapped[UuidPk]
    input: Mapped[JsonObject]
    status: Mapped[str] = mapped_column(Text)
    scenario_version_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("scenario_versions.id", ondelete="SET NULL"), index=True
    )
    solver_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(user_fk(ondelete="SET NULL"), index=True)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ContentReview(Base):
    __tablename__ = "content_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approve', 'request_changes', 'reject')", name="decision_known"
        ),
    )

    id: Mapped[UuidPk]
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(fk("scenario_versions.id"), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(user_fk(ondelete="SET NULL"), index=True)
    decision: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, server_default=text("''"))
    created_at: Mapped[CreatedAt]


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    rules: Mapped[JsonObject]
    updated_at: Mapped[UpdatedAt]


class AuditLog(Base):
    """Admin and content actions."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_ts", "ts"),
        Index("ix_audit_log_actor_id_ts", "actor_id", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(user_fk(ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    data: Mapped[JsonObject]
    ts: Mapped[CreatedAt]
