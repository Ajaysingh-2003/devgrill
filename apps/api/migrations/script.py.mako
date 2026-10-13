"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Safe-migration checklist (docs/runbooks/safe-migrations.md):
- [ ] no long locks on tables that hold data; new columns nullable (or constant default), backfill later
- [ ] indexes on tables that hold data are CONCURRENTLY, in their own migration (autocommit_block)
- [ ] no rename/retype in one step (add, dual-write, backfill, switch, drop)
- [ ] circular foreign keys added after both tables exist; enum types dropped in downgrade
- [ ] every new foreign key has an index
- [ ] upgrade -> downgrade -> upgrade works locally; `alembic check` is clean
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
