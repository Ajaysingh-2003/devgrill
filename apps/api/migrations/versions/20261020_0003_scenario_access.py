"""scenario access tier (free | pro) for plan enforcement (ADR 013)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [x] the new column has a constant default, so Postgres 11+ adds it without a table rewrite
- [x] lock_timeout is set before the ALTER: it fails fast instead of queueing behind traffic
- [x] no index (the library filters by track, status and difficulty; access is a display field)
- [x] downgrade drops the column, then the enum type it created
- [x] upgrade -> downgrade -> upgrade round trip runs in CI (tests/integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCESS = postgresql.ENUM("free", "pro", name="access", schema="app", create_type=False)


def upgrade() -> None:
    ACCESS.create(op.get_bind(), checkfirst=False)
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        "scenarios",
        sa.Column("access", ACCESS, server_default="pro", nullable=False),
        schema="app",
    )


def downgrade() -> None:
    op.drop_column("scenarios", "access", schema="app")
    ACCESS.drop(op.get_bind(), checkfirst=False)
