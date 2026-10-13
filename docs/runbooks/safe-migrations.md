# Safe database migrations

The checklist every migration follows (docs/PLAN.md §9.3). These are the same lock and backfill mistakes the Databases track teaches, so we hold ourselves to them too.

## Two schemas, two owners

| Schema | Owner | Tool | Command |
|---|---|---|---|
| `app` | DevGrill | Alembic (`apps/api/migrations`) | `just db-migrate` (step 1) |
| `auth` | Better Auth | `apps/web/scripts/auth-migrate.mts` | `just db-migrate` (step 2) |

App tables never hold foreign keys into `auth` (ADR 011). Users are referenced through `app.profiles(user_id)`.

## Writing a migration

1. Change the models in `packages/py-core/src/devgrill/infra/models/`.
2. Generate the migration against a scratch database, never against data you care about:
   ```powershell
   $env:DATABASE_URL="postgresql+asyncpg://devgrill:devgrill@localhost:5432/devgrill_scratch"
   just db-revision "add hints_used to attempts"
   ```
3. **Read every line.** Autogenerate gets these wrong:
   - **Circular foreign keys** (`use_alter=True`): `create_table` silently skips them. Add them with `op.create_foreign_key` after both tables exist, and drop them first in `downgrade`.
   - **Enum types**: `drop_table` does not drop them. Drop them in `downgrade`, or the next upgrade fails with "type already exists".
   - **Imports** for custom column types (for example `pgvector`).
4. Fill in the checklist in the migration's docstring (template in `migrations/script.py.mako`).

## The checklist

| Rule | Why |
|---|---|
| New columns on existing tables are **nullable** (or have a constant default); backfill in batches; add `NOT NULL` in a later migration | `ALTER TABLE ... ADD COLUMN ... NOT NULL` rewrites or locks the table |
| Indexes on tables that already hold data use `CREATE INDEX CONCURRENTLY`, in their own migration with `autocommit_block()` | A plain `CREATE INDEX` blocks writes for the whole build |
| No column renames or type changes in one step: add the new column, dual-write, backfill, switch reads, drop the old | Old and new code run side by side during a deploy |
| Set `lock_timeout` (for example `SET lock_timeout = '5s'`) before DDL on hot tables | Fail fast instead of queueing every query behind the lock |
| `downgrade()` works in dev, and **production only moves forward** | Rollbacks in production are new forward migrations |
| Every foreign key has an index | Deletes on the parent otherwise scan the child (checked by `test_every_foreign_key_has_an_index`) |

New tables are exempt from the lock rules, because nothing reads them yet.

## What CI checks

The `stack` job runs these steps:

1. `alembic upgrade head`, `downgrade base`, `upgrade head` on an empty database.
2. `alembic check`: the models and migrations agree, so a forgotten migration fails here.
3. `auth-migrate.mts --check`: the Better Auth schema has no pending changes.
4. The integration tests: every foreign key has an index, the circular keys exist, the one-live-attempt rule holds, and the library queries use indexes and run in under 20 ms on 10,000 scenarios.

## Resetting local data

- `just db-reset` drops **both** schemas (all local accounts and progress), re-migrates and re-seeds. It asks for confirmation first.
- Tests never use the dev database:
  - pytest uses `devgrill_test` (see `conftest.py`).
  - e2e uses `devgrill_e2e` (see `apps/web/e2e/prepare-db.mjs`).
  - Both refuse to drop any database without the matching suffix.
