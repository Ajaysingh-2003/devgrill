# 011. Data model and authentication design (phase 2)

Date: 2026-10-13 · Status: accepted

## Context
Phase 2 brings real users, the full schema (`docs/PLAN.md` §9.2) and the API that serves it. ADR 005 chose Better Auth in the web app with JWT verification in FastAPI. This ADR records how that was built, and the choices the plan left open.

## Decisions

### Schemas and identity
1. **Two schemas, two migration owners.**
   - `auth` belongs to Better Auth (`apps/web/scripts/auth-migrate.mts`).
   - `app` belongs to Alembic.
   - `just db-migrate` runs both, in that order.
2. **No foreign keys from `app` into `auth`.** Every app table that refers to a user points at `app.profiles(user_id)` (`ON DELETE CASCADE`). The schemas migrate independently, and the API's tests and tools never need Better Auth's tables. The profile row is created idempotently in two places:
   - the sign-in hook (`POST /internal/profiles`, HMAC-signed);
   - the API's first authenticated request (in its own transaction, so a failing request can't roll it back).
3. **UUID user ids** (`advanced.database.generateId: "uuid"`), so the API stores real `uuid` columns.
4. **Primary keys are `uuidv7()`** (Postgres 18), except for high-volume event tables (`attempt_events`, `rating_history`, `audit_log`), which use `bigint` identity.

### GitHub sign-in
5. **GitHub through Better Auth's generic OAuth plugin**, not the built-in provider.
   - The built-in provider hard-codes github.com.
   - The generic one reads the authorize, token and API endpoints from `GITHUB_OAUTH_URL` and `GITHUB_API_URL`.
   - Locally that is real GitHub. The e2e tests use a mock IdP (`apps/web/e2e/mock-github.mjs`). The code path is the same either way.
   - The provider id stays `github`, so the callback is `/api/auth/callback/github`.
6. **The GitHub login is stored on the user (`githubLogin`) and can never be changed afterwards**, because admin roles are granted by login (`ADMIN_GITHUB_LOGINS`).
   - The field must allow input so the OAuth profile can set it at creation; `input: false` drops it.
   - That would also let `/update-user` set it, so a `hooks.before` middleware rejects such requests with a 400.
   - A `user.update.before` database hook cancels any update that carries the field. It cancels rather than strips because Better Auth *merges* hook output into the update.
   - Email and password sign-up is disabled.
   - The e2e suite has a test for exactly this privilege escalation (it found the merge behaviour).

### Tokens and keys
7. **JWTs for the API.**
   - EdDSA (Ed25519), 15 minutes, issuer = the web origin, audience `devgrill-api`.
   - Claims: `sub`, `name`, `email`, `image`, `login`.
   - Keys rotate every 30 days, and old keys stay published for one more day.
   - The API caches the JWKS for 10 minutes and refetches on an unknown `kid` at most every 30 s, so rotation needs no coordination and forged kids can't flood the endpoint.
   - Only `EdDSA` is accepted (no algorithm confusion).
8. **Guest tokens.**
   - HS256 with their own secret and audience, so they can never pass as user tokens.
   - Held in an httpOnly cookie by the web app.
   - Attempts store only `sha256(jti)`.
   - The web app's `/auth/complete` claims guest attempts right after sign-in. Ended attempts always move; at most one live attempt moves, and only if the user has none, to keep the one-live-attempt rule.

### API behaviour
9. **One transaction per request** (`Depends(get_session, scope="function")`): the commit happens *before* the response is sent, so a failed commit is a 500, never a 200.
10. **Valkey.**
    - Rate limits are fixed windows per client IP, with IETF `RateLimit` and `RateLimit-Policy` headers, plus strict buckets for guest tokens and claims. If Valkey is down they fail open.
    - Idempotency keys are stored for 24 h, scoped by a hash of the caller's credentials. A replay of the same key with a different body is a 422; a retry while the first request is still running is a 409.
    - There is no `idempotency_keys` table.
11. **Contract precision for Schemathesis.**
    - Every error is documented as `application/problem+json`.
    - Cursors and slugs have patterns.
    - Time zones are a named enum.
    - Non-nullable PATCH fields are non-null in the schema (`SkipJsonSchema[None]`).
    - Booleans are `StrictBool`.
    - Operation ids are the handler names, so the generated client reads `listTracks`.
12. **Challenges are created on first request.** Today's and this week's challenge are built from IST windows, with deterministic scenario selection and `ON CONFLICT DO NOTHING`. A Temporal schedule replaces this when leaderboards arrive.

### Web app
13. **The browser never holds an API token.**
    - Server components call the API with the user's JWT (`lib/api.ts`), adding a per-render `X-Request-ID`.
    - Mutations are server actions wrapped in TanStack Query.
    - CORS allows only the web origin, without credentials.
14. **Content seeding.** `content/tracks.yaml` and `content/scenarios/<track>/<slug>/scenario.yaml` are validated by `devgrill.domain.spec` and versioned by content hash. A changed file makes a new immutable version; it never edits a published one.

## Consequences
- Deleting a user in Better Auth does not cascade to app data yet. Account deletion (phase 9) must call the API to delete the profile, which cascades.
- `ADMIN_GITHUB_LOGINS` is a bootstrap mechanism. An admin UI for roles comes with the content console (phase 3+).
- Rate limits keyed by IP need `--proxy-headers` behind a load balancer (deployment, Track H).
- Two migration tools: CI checks both for drift (`alembic check`, `auth-migrate --check`).
