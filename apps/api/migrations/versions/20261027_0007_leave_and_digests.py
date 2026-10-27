"""on-call leave days, the digest cap table and profile email (phase 7)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [x] two new tables, and one nullable column with no default (no rewrite)
- [x] lock_timeout is set before the ALTER
- [x] new foreign keys point at app.profiles only (ADR 011), on new, empty tables
- [x] upgrade -> downgrade -> upgrade round trip runs in CI (tests/integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("profiles", sa.Column("email", sa.Text(), nullable=True), schema="app")
    op.create_table(
        "leave_days",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.profiles.user_id"],
            name=op.f("fk_leave_days_user_id_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "day", name=op.f("pk_leave_days")),
        schema="app",
    )
    op.create_table(
        "notifications_sent",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.profiles.user_id"],
            name=op.f("fk_notifications_sent_user_id_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "kind", "day", name=op.f("pk_notifications_sent")),
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("notifications_sent", schema="app")
    op.drop_table("leave_days", schema="app")
    op.drop_column("profiles", "email", schema="app")
