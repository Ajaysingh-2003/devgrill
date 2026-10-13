# 005. Better Auth in Next.js, JWT verification in FastAPI

Date: 2026-10-13 · Status: accepted (implemented in phase 2)

## Context
The web app owns the browser session; the Python API must authorise requests statelessly. The owner chose **GitHub sign-in only** for now.

## Decision
- **Better Auth 1.7** in `apps/web` with the GitHub provider and its JWT plugin. Data lives in our Postgres, schema `auth`.
- Next server components and route handlers call FastAPI with `Authorization: Bearer <JWT>` (EdDSA). FastAPI verifies the token against cached, rotating JWKS (`/api/auth/jwks`) with PyJWT.
- The gateway uses single-use 60-second tickets issued by the API (phase 4).
- Guests get a signed httpOnly guest token for `/try`.
- Providers are config, so Google or email can be added without code changes.

## Consequences
No session lookups on every API call. Tokens expire quickly; JWKS rotation is covered by tests in phase 2.

## Alternatives considered
Auth.js v5 (maintenance-only, still beta), Clerk (paid SaaS, data outside our DB), rolling our own (not worth the risk).
