-- Runs detached in its own psql session that stays open: a migration that took its lock and
-- then hung before committing (the migration runner lost its connection to the deploy host).
-- pg_stat_activity shows `migrator`, idle in transaction, holding an AccessExclusiveLock on
-- orders from the ALTER TABLE; pg_terminate_backend(pid) ends it (the change rolls back).
SET application_name = 'migrator';
BEGIN;
-- 20261028_0042_fulfilment: add fulfilment columns to orders
ALTER TABLE orders ADD COLUMN fulfilment_status text;
ALTER TABLE orders ADD COLUMN fulfilment_updated_at timestamptz;
\! sleep 3600
COMMIT;
