# Phase 0 QC report: Foundations and scaffold

Date: 2026-10-13 · Result: **PASS** (branch protection blocked by GitHub plan; see item 4)

## Gate checklist (docs/PLAN.md §15, Phase 0)

| # | Gate item | Result | Evidence |
|---|---|---|---|
| 1 | Fresh clone to `just dev` in ≤ 15 min on this Windows machine (PowerShell); same steps proven on Linux by CI | ✅ local · ⏳ CI | Fresh copy of every non-ignored file into a new folder (no `.env`, `.venv` or `node_modules`): `just setup` **128 s**, `just dev` + `just smoke` **49 s**. Total ≈ 3 min. Caveat: Docker images and the pnpm/uv caches were warm; a cold machine adds image pulls (≈ 1 GB) |
| 2 | No CRLF in `*.sh`, `Dockerfile*`, `*.yaml` (CI check) | ✅ | `just eol-check` passes on every text file, not just those types. CI `hygiene` job runs it |
| 3 | `/readyz` reports DB, Valkey and Temporal OK; Temporal `Ping` completes; web root renders | ✅ | `just smoke`: readyz 200 (database 85 ms, valkey 33 ms, temporal 23 ms), gateway 200, web 200 with brand, `PingWorkflow → pong:smoke` |
| 4 | CI green on an empty PR; branch protection on | ✅ CI · ⚠️ protection | Private repo `Ajaysingh-2003/devgrill`. First run: 5/6 jobs green (including the Linux full-stack smoke and the Windows unit job); `hygiene` failed on a pip-audit flag (needs hashed requirements), fixed in the follow-up commit. **Branch protection is unavailable**: GitHub returns 403 "Upgrade to GitHub Pro or make this repository public" for private repos on the Free plan. Mitigation until then: always merge through PRs with green CI |
| 5 | `pnpm gen:api` is deterministic | ✅ | Two consecutive runs: byte-identical `openapi.json` and `src/gen` |
| 6 | gitleaks clean; `.env` git-ignored; `.env.example` complete | ✅ | `just secrets`: no leaks (1.43 MB scanned). `git check-ignore .env` → `.gitignore:2` |
| 7 | ADRs 001–008 merged | ✅ written (plus ADR 009) · ⏳ merge | `docs/adr/001…009`. Nothing is committed yet (awaiting owner go-ahead) |
| 8 | Vendored skills present with `VENDORED.md`; `CLAUDE.md` references them | ✅ | `.claude/skills/` (14 skills); `CLAUDE.md` §UI work |

## Quality results (main repo, final run)

| Check | Result |
|---|---|
| ruff check / format | All checks passed · 176 files formatted |
| basedpyright (standard; strict on `devgrill.domain`) | 0 errors, 0 warnings |
| ESLint (eslint-config-next 16.4) | clean |
| TypeScript (`next typegen && tsc`, 4 packages) | clean |
| pytest unit | 26 passed |
| pytest integration (real Postgres, Valkey, Temporal) | 2 passed |
| Coverage (all Python) | 78% (entry-point `__main__` modules account for most of the gap; targets apply from phase 2) |
| Alembic | upgrade → downgrade → upgrade on Postgres 18.6; extensions `citext`, `vector`, `pg_stat_statements` present |
| Next.js production build | ✓ (`/` prerendered static) |
| pip-audit | No known vulnerabilities |
| pnpm audit (high) | 0 open. js-yaml forced to 4.3.2 via override (3 advisories fixed); GHSA-vfj7-8cjw-p6xm (`braces`, dev-only via eslint-config-next, no patch exists) accepted and recorded in `pnpm-workspace.yaml` |
| gitleaks | no leaks |
| actionlint (CI workflow) | clean |

## Bugs caught during the phase

- Temporal activity logged `extra={"name": …}` → `KeyError` (reserved LogRecord key). Caught by the unit test; fixed.
- `API_CORS_ORIGINS` as a JSON list broke under `just`'s dotenv loader. Changed to a comma-separated string with a `cors_origins` property and a test.
- Web dev server returned 500: `@devgrill/tokens` was imported but not declared as a dependency (the production build hid it). Fixed; smoke test now covers the dev server.
- Temporal container couldn't write SQLite (root-owned volume vs uid 1000). Volume now mounts on `/home/temporal`.
- A bulk CRLF conversion touched `favicon.ico`; restored byte-identical from the Next template, and `eol-fix` now skips binaries (known extensions + NUL-byte detection).
- `turbo.json` schema URL and outputs corrected against the bundled Turborepo docs.

## Deviations from the plan (all recorded in ADRs or the plan)

| Planned | Actual | Why |
|---|---|---|
| MinIO for object storage | SeaweedFS 4.48 (S3 API) | MinIO no longer publishes `minio/minio` on Docker Hub (ADR 009) |
| `make` / `concurrently` | `just` + `scripts/dev.py` (no shell) | cmd.exe is blocked by group policy (ADR 009) |
| `UV_NATIVE_TLS` | `UV_SYSTEM_CERTS` | Renamed in uv 0.13 |
| shadcn init in phase 0 | Deferred to phase 1 | The shadcn CLI runs via `pnpm dlx` (cmd-based). `packages/ui` has the `cn` helper; phase 1 runs the CLI via `node` directly |
| Prettier | Deferred to phase 1 | Added with the design-system code (Tailwind class sorting) (ADR 008) |
| ESLint 10 | ESLint 9 | What `create-next-app` 16.4 / `eslint-config-next` ships |
| `httpx` for tests | `httpx2` | Starlette 1.8 deprecates `httpx` in its test client |

## Machine changes made (user-level, documented in README and ADR 009)

- User env var `NODE_OPTIONS=--use-system-ca`.
- User PATH: appended `%APPDATA%\Python\Python314\Scripts`.
- npm and pnpm user config: `script-shell = C:\Program Files\Git\bin\bash.exe`.
- Installed `uv 0.13.0` and `just 1.58.0` (pip `--user`), `pnpm 12.11.2` (npm global).
- Local repo config: `core.autocrlf=false`.
- Docker: images pulled; `devgrill-dev` compose project running (5 healthy services).

## Owner follow-ups

1. Branch protection needs GitHub Pro (or a public repo). Decide whether to upgrade; until then, use PRs with green CI as a convention.
2. Optional: ask IT to allow `cmd.exe` for development. This would remove the need for the workarounds in ADR 009, but nothing depends on it.
