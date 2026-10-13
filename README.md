# DevGrill

_Get grilled before prod does._ A flight simulator for on-call: engineers investigate live broken systems in the browser, mitigate, fix the root cause, pass a verify step that replays traffic and chaos probes, and write a postmortem graded by AI.

Private and proprietary. See [LICENSE](LICENSE).

- Plan: [docs/PLAN.md](docs/PLAN.md)
- Architecture decisions: [docs/adr/](docs/adr/)
- QC reports: [docs/qc/](docs/qc/)

## Status

**Phase 0 (scaffold) complete.** The monorepo builds, the platform services run in Docker, and api, worker, gateway and web start together and pass the smoke test.

**Phase 1 (design system and app shell) complete.** Tokens with a contrast gate, the component library in Storybook, and every page template as a static, clickable prototype in both themes (mock data). See `docs/design/system.md` and `docs/qc/phase-1.md`.

## Stack

| Layer     | Tech                                                                        |
| --------- | --------------------------------------------------------------------------- |
| Web       | Next.js 16.4 (App Router, Turbopack), React 19.3, Tailwind v4, TypeScript 6 |
| API       | FastAPI 0.143 on Python 3.14, SQLAlchemy 2.1 async + asyncpg, Alembic       |
| Workflows | Temporal (Python SDK 1.34; dev server in Docker)                            |
| Gateway   | FastAPI WebSockets (terminal and telemetry from phase 4)                    |
| Data      | Postgres 18 + pgvector 0.8.7, Valkey 9.1, SeaweedFS (S3 API)                |
| Tooling   | uv workspace, pnpm 12 + Turborepo, just, ruff, basedpyright, ESLint, pytest |

## Layout

```
apps/        web (Next.js) · api (FastAPI) · gateway · worker (Temporal)
packages/    py-core (devgrill: domain + infra) · py-content (scenario CLI)
             ui · tokens · config · api-client (generated)
content/     scenarios, base apps, faults (phase 3)
infra/       docker compose for local platform services
scripts/     dev runner, smoke test, setup and line-ending checks
docs/        plan, ADRs, QC reports
```

## Setup (Windows, native)

This machine has constraints (corporate TLS proxy, `cmd.exe` blocked by policy). The one-time user-level setup is already done here; on a new machine:

1. Install **Docker Desktop**, **Node 24**, **Python 3.14**, **Git for Windows**.
2. Trust the Windows certificate store and avoid cmd.exe:
   ```powershell
   setx NODE_OPTIONS "--use-system-ca"
   npm config set script-shell "C:\Program Files\Git\bin\bash.exe" --location=user
   pnpm config set script-shell "C:\Program Files\Git\bin\bash.exe"
   git config --global core.autocrlf false
   ```
3. Install the tools (winget is unavailable here, so use PyPI and npm):
   ```powershell
   python -m pip install --user uv rust-just
   npm install -g pnpm@12
   ```
   Make sure `%APPDATA%\Python\Python314\Scripts` is on your user PATH, then open a new terminal.
4. In the repo:
   ```powershell
   just setup      # uv sync, .env from .env.example, pnpm install, services up, migrate
   just dev        # api :8000 · gateway :8100 · web :3000 · worker
   just smoke      # in a second terminal: checks the running stack end to end
   ```

On Linux or macOS, steps 2–3 are just "install uv, just and pnpm"; everything else is identical.

## Everyday commands

| Command                                                         | What it does                                                    |
| --------------------------------------------------------------- | --------------------------------------------------------------- |
| `just`                                                          | List all recipes                                                |
| `just dev` / `just run api worker`                              | Run everything / a subset                                       |
| `just deps-up` / `deps-down` / `deps-ps` / `deps-logs temporal` | Platform services                                               |
| `just db-migrate` / `db-revision "msg"` / `db-reset`            | Database migrations                                             |
| `just test` / `test-int` / `test-cov`                           | Python unit / integration / coverage                            |
| `just lint` / `types` / `fmt`                                   | Lint, type-check, format                                        |
| `just gen` / `gen-check`                                        | Regenerate the OpenAPI spec and TS client / fail on drift       |
| `just eol-check` / `eol-fix`                                    | Enforce LF line endings                                         |
| `just storybook` / `test-web` / `e2e`                           | Component library / story + axe tests / browser e2e             |
| `just tokens` / `colors-check` / `fmt-web`                      | Regenerate tokens (contrast gate) / raw-colour guard / Prettier |
| `just check`                                                    | Everything CI's fast jobs run                                   |

## Local URLs

| Service           | URL                          |
| ----------------- | ---------------------------- |
| Web               | http://localhost:3000        |
| API docs          | http://localhost:8000/docs   |
| API readiness     | http://localhost:8000/readyz |
| Temporal UI       | http://localhost:8233        |
| Mailpit           | http://localhost:8025        |
| Object store (S3) | http://localhost:8333        |

## Conventions

- Errors are RFC 9457 `application/problem+json`; every response has `x-request-id`.
- The OpenAPI spec is the contract; `packages/api-client/src/gen` is generated, never hand-edited.
- LF line endings everywhere (CI enforces it).
- Python tools run as `python -m <tool>` (venv launchers can be blocked on managed Windows).
- UI work uses the vendored skills in `.claude/skills` (see [VENDORED.md](.claude/skills/VENDORED.md)).
