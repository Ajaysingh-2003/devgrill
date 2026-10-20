SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE query ILIKE '%pg_sleep(3600)%' AND pid <> pg_backend_pid();
