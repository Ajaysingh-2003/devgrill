"""case file plays: a player's first answers to a case file (phase 7, ADR 018)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [x] a new table: nothing reads it yet, so the lock rules don't apply
- [x] no enum types, no circular foreign keys
- [x] both foreign keys have an index (the unique constraint leads with user_id)
- [x] upgrade -> downgrade -> upgrade round trip runs in CI (tests/integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_file_plays",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "choices",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("write_up", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name=op.f("ck_case_file_plays_score_range")),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["app.scenarios.id"],
            name=op.f("fk_case_file_plays_scenario_id_scenarios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.profiles.user_id"],
            name=op.f("fk_case_file_plays_user_id_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_file_plays")),
        sa.UniqueConstraint(
            "user_id", "scenario_id", name="uq_case_file_plays_user_id_scenario_id"
        ),
        schema="app",
    )
    op.create_index(
        op.f("ix_case_file_plays_scenario_id"),
        "case_file_plays",
        ["scenario_id"],
        unique=False,
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_case_file_plays_scenario_id"), table_name="case_file_plays", schema="app"
    )
    op.drop_table("case_file_plays", schema="app")
