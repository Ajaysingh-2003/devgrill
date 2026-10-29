-- A nightly report: one long repeatable-read transaction, so its snapshot stays open while it
-- works. A concurrent index build has to wait for snapshots older than itself before it can
-- mark the index valid (any table: a snapshot covers the whole database).
SET application_name = 'nightly-report';
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT status, count(*) FROM orders GROUP BY status;
\! sleep 4
-- (In the sandbox this session also plays the migration runner's watchdog, which cancels any
-- step running longer than a few seconds and logs it as a warning, not a failure.)
SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE application_name = 'migrator';
\! sleep 2
COMMIT;
