# 004. Valkey for cache, pub/sub, rate limits and leaderboards

Date: 2026-10-13 · Status: accepted

## Context
We need a fast key-value store for rate limits, idempotency keys, telemetry fan-out (pub/sub), short-lived tickets and leaderboards (sorted sets).

## Decision
**Valkey 9.1** (`valkey/valkey:9.1`), BSD-licensed and wire-compatible with Redis. Python uses the `redis` 8.1 client (`redis.asyncio`). Locally persistence is off (`--save "" --appendonly no`): the cache is never a source of truth.

## Consequences
Redis 8 is AGPLv3 again, which legal teams often block; Valkey avoids the question. Every key is namespaced and has a TTL.

## Alternatives considered
Redis 8 (licence), KeyDB (less active), Postgres-only (`LISTEN/NOTIFY` doesn't scale well for telemetry fan-out).
