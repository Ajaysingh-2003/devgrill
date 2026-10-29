-- The migration as shipped: drop the old index first, then build the covering replacement
-- concurrently. The build has to wait for the nightly report's older snapshot; the runner's
-- watchdog cancels the step after a few seconds (and logs a warning, not a failure), and
-- Postgres leaves the new index behind INVALID: it shows in \d reviews, but the planner
-- can't use it.
SELECT pg_sleep(1); -- the report has its snapshot
SET application_name = 'migrator';
-- 20261029_0044_reviews_covering_index: replace the product index with a covering one
DROP INDEX IF EXISTS reviews_product_id_idx;
\set ON_ERROR_STOP off
CREATE INDEX CONCURRENTLY reviews_product_id_rating_idx ON reviews (product_id) INCLUDE (rating);
