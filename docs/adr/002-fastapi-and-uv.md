# 002. FastAPI on Python 3.14, managed with uv

Date: 2026-10-13 · Status: accepted

## Context
The owner is an AI/ML engineer; the product is AI-heavy (mentor, grading, generator/solver agents). The API is mostly I/O-bound (Postgres, Valkey, Temporal, Docker, OpenAI).

## Decision
- **Python 3.14** (pinned `>=3.14,<3.15`; `.python-version`). uv 0.13 would otherwise default to 3.15.
- **FastAPI 0.143** + Pydantic 2.14 + pydantic-settings, served by uvicorn 0.54 (asyncio loop; uvloop has no Windows build).
- **SQLAlchemy 2.1 async + asyncpg**, Alembic 1.20 with an async env. Alembic owns only the `app` schema; Better Auth owns `auth`.
- **uv 0.13 workspace** with exact pins for core libraries; the lockfile pins everything else.
- Errors are RFC 9457 `application/problem+json`. Every response carries `x-request-id`.
- Lint: ruff 0.17. Types: basedpyright 1.40 (`standard`; `strict` for `devgrill.domain`).

## Consequences
- FastAPI is still 0.x, so we pin exactly and upgrade deliberately via Dependabot PRs.
- Starlette 1.8 deprecates `httpx` in its test client, so tests use `httpx2`.

## Alternatives considered
TypeScript (NestJS/Fastify): one language, weaker ML ecosystem. Go: excellent for the gateway later (see ADR 007), slower to iterate on AI features.
