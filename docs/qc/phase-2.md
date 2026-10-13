# Phase 2 QC report: Domain, database, auth and API skeleton

Date: 2026-10-13 · Result: **PASS with recorded deviations** (see "Deviations"). Decisions: ADR 011. Runbooks: `docs/runbooks/github-oauth.md`, `docs/runbooks/safe-migrations.md`.

## What was built

- **Schema:**
  - 37 tables in `app` (identity, catalog, play, progression, platform; `docs/PLAN.md` §9.2) in one reviewed Alembic migration, with 18 enum types.
  - The one-live-attempt partial unique index, a GIN index on tags, an HNSW index on approach embeddings, and an index on every foreign key.
  - Better Auth's 5 tables in `auth`.
- **Domain (`devgrill.domain`, pure, strict-typed):** enums, the attempt state machine, Glicko-2, verify scoring, streaks (IST rollover, freezes, weekly mode) and the content spec models.
- **API:**
  - 17 `/v1` operations: catalog, briefing, approaches (resolved players only), daily and weekly challenges, `/me` (profile, prefs, ratings, progress, streak, attempts), guest tokens and claiming, public profiles, admin scenarios.
  - The HMAC-signed `/internal/profiles` hook.
  - Every error is RFC 9457 problem+json.
- **Auth:**
  - GitHub through Better Auth's generic OAuth plugin, with sessions in `auth`.
  - EdDSA JWTs for the API (rotating JWKS, cached and refetched on an unknown `kid`).
  - Guest tokens in an httpOnly cookie, claimed after sign-in.
  - Admin roles from `ADMIN_GITHUB_LOGINS`.
- **Platform:**
  - Unit of work per request (committed before the response).
  - Valkey rate limits with IETF headers.
  - Idempotency keys.
  - CORS limited to the web origin, without credentials.
  - Request ids propagated from web to API.
- **Content:** `content/tracks.yaml` (8 tracks, 27 topics) and 12 placeholder scenarios, seeded with `just db-seed`, idempotent and versioned by content hash.
- **Web:**
  - Sign-in and sign-out.
  - Library, track, briefing, daily, profile, settings and admin pages on real data, with Suspense loading states and error boundaries.
  - Preferences saved to the profile and adopted on new devices.
  - Pro mode saved.
  - The generated client is used server-side, with TanStack Query for mutations.

## Gate checklist (docs/PLAN.md §15, Phase 2)

| # | Gate item | Result | Evidence |
|---|---|---|---|
| 1 | Auth e2e: GitHub flow (mocked IdP in CI), sign-out, session expiry, guest token issuance, guest → account claim | ✅ | `apps/web/e2e/auth.spec.ts` against a mock GitHub (`e2e/mock-github.mjs`), the production web build, the API and a dedicated `devgrill_e2e` database. It also covers off-site `next` redirects, the admin role, prefs following the account, cross-site requests refused, and the GitHub login being immutable. Real GitHub locally needs your OAuth App (runbook) and hasn't been exercised by me |
| 2 | Expired, tampered and wrong-audience JWTs → 401; JWKS rotation tested | ✅ | `apps/api/tests/test_auth_tokens.py` (12): expired, tampered payload, wrong audience and issuer, `HS256` and `none` algorithm confusion, garbage tokens, rotation on the first unknown `kid`, forged kids can't force refetches, JWKS outage keeps known keys. `test_api.py`: the same as HTTP 401s with `WWW-Authenticate` |
| 3 | Schemathesis passes for all `/v1` endpoints; contract drift check passes | ✅ | `apps/api/tests/test_contract.py`: all 17 `/v1` operations fuzzed against a live server; CI `codegen` job: no drift. Schemathesis found **five real defects**, all fixed (below) |
| 4 | Migrations: up → down → up on an empty DB; safe-migration checklist; `EXPLAIN` for library queries (index use, < 20 ms on 10k scenarios) | ✅ | `test_migrations.py`: round trip, `alembic check` (models = migrations), every FK indexed, circular FKs present, DB-enforced rules. `test_query_plans.py`: 5 library queries on 10,000 scenarios are under 20 ms (warm), and paginated ones never sequential-scan `scenarios`. Checklist: `docs/runbooks/safe-migrations.md`, also in the migration template |
| 5 | Glicko-2 matches Glickman's worked example to 1e-4 | ✅ | `test_glicko2.py`: μ′ = −0.2069, φ′ = 0.8722, σ′ = 0.05999 (r′ = 1464.05, RD′ = 151.52), plus 5 Hypothesis properties |
| 6 | OWASP: authz test for every admin route (403 for non-admin); rate limits enforced; CORS restricted | ✅ | `test_api.py`: every `/v1/admin` route is 401 anonymous, 403 for a user and 200 for an admin, and a meta-test fails if a new admin route isn't in the list. Rate limits: default bucket 429 with `Retry-After`; guest-token bucket. CORS: web origin only, no credentials |
| 7 | Standard UI QC (§14.5) for library, track, briefing, profile, settings with real data, including loading and error states | ✅ with notes | axe (WCAG 2.2 AA) on every anonymous page in both themes, and on the signed-in pages and the admin console (`e2e/a11y-signed-in.spec.ts`). Screenshots in `docs/design/qc/phase-2/`. Loading: Suspense skeletons per section. Errors: `(app)/error.tsx` keeps the shell; 404s go to the not-found page. See "UI notes" |

## Defects found by the gates (all fixed)

| Found by | Defect | Fix |
|---|---|---|
| Migration review | Autogenerate put the two circular foreign keys inline with `use_alter`, and `CREATE TABLE` skips those, so they would never have existed | Explicit `create_foreign_key` after both tables; a test asserts they exist |
| Migration review | The downgrade didn't drop the 18 enum types, so the next upgrade fails | Drops them; the round trip runs in CI |
| API tests | A lazily created profile was rolled back whenever the same request then failed (for example a 403) | Created in its own transaction |
| Schemathesis | `PATCH /v1/me {"is_public": null}` → 500 (NOT NULL violation) | Non-nullable fields reject null (422), and the schema says so |
| Schemathesis | A NUL byte in `q` → 500 (Postgres rejects `\x00`) | Patterns on search text, slugs and handles |
| Schemathesis | `OPTIONS /v1/me` → 405 with `Allow: GET`, although PATCH exists | `Allow` computed from the OpenAPI paths |
| Schemathesis | `"pro_mode": 0` accepted as `false` | `StrictBool` and `extra="forbid"` on request bodies |
| Schemathesis | The empty-string time zone was schema-valid but rejected | Time zones published as an enum |
| e2e | The GitHub login was silently dropped on sign-up, so admin roles never applied | The field is allowed at creation and blocked afterwards |
| e2e (security test) | **Privilege escalation:** `POST /api/auth/update-user {"githubLogin": "<admin>"}` changed the login. Better Auth merges hook output, so stripping the key did nothing | Endpoint middleware rejects it (400); the DB hook cancels any update carrying it; regression test |
| e2e | Clicking sign-in before hydration did nothing; a failed sign-in left the button stuck | Test waits for hydration; the button recovers from errors |
| e2e | `crypto.randomUUID()` during prerender (Next 16) | `connection()` before API calls |
| e2e (local) | Intermittent `connect ETIMEDOUT` to Postgres from the web server: idle-connection churn through Docker Desktop's port proxy | Warm pool (`idleTimeoutMillis` 5 min, keep-alive, 10 s connect timeout) |
| e2e (local) | Sign-ins stalled at random under parallel tests: Better Auth's own limiter allows 3 sign-ins per 10 s per IP, and every test browser is 127.0.0.1 | Kept on everywhere; only the e2e stack sets `AUTH_RATE_LIMIT=off` |
| CI | The smoke step could hang for an hour after passing (background stack kept it open) | Own process group, killed on exit; every job capped at 30 min |

## Quality results (final run)

| Check | Result |
|---|---|
| ruff, ruff format, basedpyright (strict on the domain) | clean |
| pytest unit + integration (real Postgres and Valkey) | 116 passed + 17 Schemathesis operation runs (twice in a row) |
| Schemathesis (17 `/v1` operations, live server) | clean |
| Query plans on 10k scenarios | all < 20 ms, index scans |
| TypeScript, ESLint, Prettier, colour guard (web) | clean (135 UI files on semantic tokens) |
| Next.js production build | ✓ |
| Playwright e2e (auth, axe on every page in both themes, keyboard, motion) | 53/53, three clean runs in a row after the fixes below (each on a freshly built database) |

## Deviations

- **Sentry in the web app is deferred to phase 8.** The API already reports to Sentry when `SENTRY_DSN` is set (phase 0). The web side has no DSN or hosting yet; wiring `@sentry/nextjs` now would add config for nothing to report to. Request ids already tie web logs to API logs.
- **Browser → API calls aren't used yet.** The API supports them (CORS, bearer JWT via `/api/auth/token`), but every read is server-side and every write is a server action, so the browser never holds an API token. TanStack Query wraps those server actions.
- **Real GitHub not exercised in CI** (by design: mock IdP). Locally it needs your OAuth App.
- **Profile visibility:** profiles are public by default (`is_public`); the setting is in the API but not yet on the settings page (phase 7, with leagues).

## UI notes

- **Library:**
  - signed out: "The system map", scenario counts, a "Sign in to track your progress" prompt;
  - signed in: mastery rings, solved counts, ratings once earned, "Pick up where you left off".
- **Briefing:** the story, system and goals come from the scenario spec. Solve rate appears only after 10 ended attempts; small samples mislead. The warm-up link points to an easier scenario in the same track.
- **Daily incident:** the same scenario for everyone, from midnight IST.
- **Settings:** changes save immediately. Theme and motion also follow you to new browsers, because the profile wins on first load and later changes are saved.
- **Still mock data (by plan):** workspace, debrief, postmortem and Quick Fire (phases 4–7). The landing page stays static for performance.
