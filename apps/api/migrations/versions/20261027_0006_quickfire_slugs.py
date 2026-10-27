"""quickfire cards get a slug: content is upserted by it (phase 7)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [x] the table has no rows before phase 7 (nothing wrote cards); any that exist get their id as
      a slug before NOT NULL, so the upgrade can't fail on them
- [x] lock_timeout is set before the ALTERs
- [x] the unique constraint builds on an empty (or tiny) table: no CONCURRENTLY needed
- [x] upgrade -> downgrade -> upgrade round trip runs in CI (tests/integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("quickfire_cards", sa.Column("slug", sa.Text(), nullable=True), schema="app")
    op.execute("UPDATE app.quickfire_cards SET slug = id::text WHERE slug IS NULL")
    op.alter_column("quickfire_cards", "slug", nullable=False, schema="app")
    op.create_unique_constraint(
        op.f("uq_quickfire_cards_slug"), "quickfire_cards", ["slug"], schema="app"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint(op.f("uq_quickfire_cards_slug"), "quickfire_cards", schema="app")
    op.drop_column("quickfire_cards", "slug", schema="app")
