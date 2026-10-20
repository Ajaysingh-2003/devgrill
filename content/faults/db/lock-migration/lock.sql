-- Runs detached in its own psql session that stays open: a migration that locked the table
-- and then stalled. pg_stat_activity shows it running pg_sleep while holding an
-- AccessExclusiveLock on orders; pg_terminate_backend(pid) is the way out.
BEGIN;
LOCK TABLE orders IN ACCESS EXCLUSIVE MODE;
SELECT pg_sleep(3600);
