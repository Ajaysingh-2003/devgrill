# 003. Temporal for sandbox lifecycle and background work

Date: 2026-10-13 · Status: accepted

## Context
A sandbox goes through provision → health wait → fault injection → active with TTL and idle timers → verify → **guaranteed teardown**, even if a worker crashes mid-way. Leaked sandboxes cost money and capacity.

## Decision
Use **Temporal** (Python SDK 1.34). Locally it runs as the Temporal CLI dev server in Docker (`temporalio/temporal:1.9.1` = Server 1.32.0). Short jobs (grading, classification) are activities too, so there is one job system.

## Consequences
- Durable timers, signals (extend, reset, abandon, verify) and teardown in `finally`.
- Workflows must be deterministic: I/O only in activities. Imports pass through `workflow.unsafe.imports_passed_through()`.
- Activity log calls must not use reserved LogRecord keys such as `name` (a phase 0 unit test caught this).
- Production needs Temporal on Postgres or Temporal Cloud (Track H).

## Alternatives considered
Hatchet (Postgres-only, simpler but younger), arq or Celery (no durable workflows), Taskiq or Dramatiq (short tasks only).
