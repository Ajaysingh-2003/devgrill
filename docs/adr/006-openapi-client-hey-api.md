# 006. OpenAPI is the contract; TS client generated with Hey API

Date: 2026-10-13 · Status: accepted

## Context
The web app must call the API with types that cannot drift from the backend.

## Decision
- FastAPI's OpenAPI document is exported **deterministically** (`devgrill_api.openapi_export`: sorted keys, LF, no lifespan or network).
- `@hey-api/openapi-ts` 0.99 (exact pin) generates `packages/api-client/src/gen` with the `client-fetch`, `typescript` and `sdk` plugins. The TanStack Query and zod plugins are added in phase 2.
- `pnpm gen:api` (or `just gen`) regenerates both. CI's `codegen` job fails on any diff.
- Generated files are committed and marked `linguist-generated`; never edit them by hand.

## Consequences
API changes and client changes land in the same PR. Hey API is 0.x, so it's pinned exactly and upgraded deliberately.

## Alternatives considered
orval (good, more config), openapi-typescript + openapi-fetch (slower release cadence).
