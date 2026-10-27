"""public profiles become opt-in: new profiles default to private (phase 7)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [x] only the column default changes: no rewrite, and existing rows keep their value (existing
      players stay public until they change it in Settings)
- [x] lock_timeout is set before the ALTER
- [x] no index, no rename/retype, no new foreign key
- [x] upgrade -> downgrade -> upgrade round trip runs in CI (tests/integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.alter_column("profiles", "is_public", server_default=sa.text("false"), schema="app")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.alter_column("profiles", "is_public", server_default=sa.text("true"), schema="app")
