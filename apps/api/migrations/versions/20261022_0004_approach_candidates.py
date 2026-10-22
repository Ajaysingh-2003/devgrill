"""approach candidates: fixes the classifier didn't recognise, for the admin queue (ADR 016)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [x] a new table only: nothing reads it yet, so no lock rules apply
- [x] no index on a table that holds data
- [x] no rename/retype
- [x] no circular foreign keys (attempts and approaches already exist); no new enum types
- [x] every new foreign key has an index (attempt_id through its unique constraint)
- [x] upgrade -> downgrade -> upgrade round trip runs in CI (tests/integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approach_candidates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("approach_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'promoted', 'dismissed')",
            name=op.f("ck_approach_candidates_status_known"),
        ),
        sa.ForeignKeyConstraint(
            ["approach_id"],
            ["app.approaches.id"],
            name=op.f("fk_approach_candidates_approach_id_approaches"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["app.attempts.id"],
            name=op.f("fk_approach_candidates_attempt_id_attempts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["app.scenarios.id"],
            name=op.f("fk_approach_candidates_scenario_id_scenarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approach_candidates")),
        sa.UniqueConstraint("attempt_id", name=op.f("uq_approach_candidates_attempt_id")),
        schema="app",
    )
    op.create_index(
        op.f("ix_approach_candidates_approach_id"),
        "approach_candidates",
        ["approach_id"],
        unique=False,
        schema="app",
    )
    op.create_index(
        op.f("ix_approach_candidates_scenario_id"),
        "approach_candidates",
        ["scenario_id"],
        unique=False,
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_approach_candidates_scenario_id"), table_name="approach_candidates", schema="app"
    )
    op.drop_index(
        op.f("ix_approach_candidates_approach_id"), table_name="approach_candidates", schema="app"
    )
    op.drop_table("approach_candidates", schema="app")
