# DevGrill task runner. Works natively on Windows (PowerShell) and on Linux/macOS (sh).
# Each recipe line runs on its own, and a failing line stops the recipe.
# List recipes: just

set dotenv-load := true
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

compose := "docker compose -f infra/compose/docker-compose.dev.yml"
alembic := "uv run python -m alembic -c apps/api/alembic.ini"

default:
    @just --list --unsorted

# ---------------------------------------------------------------- setup

# Install dependencies, create .env (with generated secrets), start services, migrate, seed.
setup:
    uv sync --all-packages
    uv run python scripts/setup.py
    pnpm install
    just deps-up
    just db-migrate
    just db-seed

# ------------------------------------------------------- platform services

# Start Postgres, Valkey, Temporal, object store and Mailpit; wait until healthy.
deps-up:
    {{compose}} up -d --wait

# Stop platform services (data is kept).
deps-down:
    {{compose}} down

# Stop platform services AND delete their data volumes.
[confirm("Delete all local Postgres/Temporal/object-store data? (y/N)")]
deps-nuke:
    {{compose}} down -v

# Follow logs of platform services (optionally one: just deps-logs temporal).
deps-logs service="":
    {{compose}} logs -f {{service}}

# Show platform service health.
deps-ps:
    {{compose}} ps

# Langfuse (LLM traces, optional): after deps-up; UI on http://localhost:3400.
langfuse-up:
    docker compose -f infra/compose/docker-compose.langfuse.yml up -d --wait

langfuse-down:
    docker compose -f infra/compose/docker-compose.langfuse.yml down

# ------------------------------------------------------------------- AI

# AI evals against the real models (needs OPENAI_API_KEY): just evals, or just evals persona --limit 5
evals *args:
    uv run python -m evals {{args}}

# ----------------------------------------------------------------- run

# Start services, migrate, then run api + worker + gateway + web together.
dev: deps-up db-migrate
    uv run python scripts/dev.py

# Run a subset, e.g. `just run api worker`.
run +names:
    uv run python scripts/dev.py {{names}}

# Execute the Temporal PingWorkflow once (needs a running worker).
ping:
    uv run python -m devgrill_worker ping

# Smoke-test a running stack (api readiness, gateway, web, Temporal ping).
smoke:
    uv run python scripts/smoke.py

# ------------------------------------------------------------- database

# Apply all migrations: Alembic owns schema `app`, Better Auth owns schema `auth`.
db-migrate:
    {{alembic}} upgrade head
    node apps/web/scripts/auth-migrate.mts

# Load content/ (tracks, topics, scenarios) into the database. Safe to re-run.
db-seed:
    uv run python -m devgrill_content.cli seed

# Roll back one migration.
db-downgrade:
    {{alembic}} downgrade -1

# Create a new migration: just db-revision "add attempts table"
db-revision message:
    {{alembic}} revision --autogenerate -m "{{message}}"

# Drop both schemas (app data AND accounts/sessions) and re-apply all migrations, then seed.
[confirm("Drop and recreate the app and auth schemas, deleting all local data? (y/N)")]
db-reset:
    {{alembic}} downgrade base
    {{alembic}} upgrade head
    node apps/web/scripts/auth-migrate.mts --reset
    just db-seed

# --------------------------------------------------------------- quality

# Python unit tests (fast, no services needed).
test:
    uv run python -m pytest -m "not integration"

# Python integration tests (needs `just deps-up`).
test-int:
    uv run python -m pytest -m integration

# All Python tests with coverage.
test-cov:
    uv run python -m pytest --cov=devgrill --cov=devgrill_api --cov=devgrill_worker --cov=devgrill_gateway --cov-report=term-missing

# Lint Python and web.
lint:
    uv run python -m ruff check .
    uv run python -m ruff format --check .
    pnpm lint

# Type-check Python and TypeScript.
types:
    uv run python -m basedpyright
    pnpm typecheck

# Auto-format Python.
fmt:
    uv run python -m ruff format .
    uv run python -m ruff check --fix .

# Regenerate the OpenAPI spec and the TypeScript client.
gen:
    pnpm gen:api

# Fail if generated code is stale.
gen-check: gen
    git diff --exit-code -- packages/api-client

# Fail on CRLF line endings.
eol-check:
    uv run python scripts/check_eol.py

# Scan the working tree for secrets (gitleaks in Docker; ignores gitignored build/deps folders).
secrets:
    docker run --rm -v "{{justfile_directory()}}:/repo" zricethezav/gitleaks:latest dir /repo --no-banner --redact --config /repo/.gitleaks.toml

# Convert CRLF to LF in text files (binaries are skipped).
eol-fix:
    uv run python scripts/check_eol.py --fix

# Production build of the web app.
build:
    pnpm build

# ---------------------------------------------------------- design system

# Regenerate design tokens (fails if any colour pair misses its contrast target).
tokens:
    pnpm --filter @devgrill/tokens build

# Component tests: unit + every Storybook story in Chromium with an axe audit.
test-web:
    pnpm test

# Storybook on http://localhost:6006
storybook:
    pnpm storybook

# Static Storybook build (packages/ui/storybook-static).
storybook-build:
    pnpm --filter @devgrill/ui build-storybook

# Browser e2e on its own database (devgrill_e2e) with a mock GitHub: auth flows, axe on every
# page in both themes, keyboard flows. Needs `just deps-up`; builds the web app first.
e2e: build
    pnpm e2e

# Fail on raw colour values outside the token system.
colors-check:
    pnpm colors:check

# Format TypeScript, CSS, JSON and Markdown with Prettier.
fmt-web:
    pnpm format

# Fail if Prettier would change anything.
fmt-web-check:
    pnpm format:check

# Screenshot matrix for design QC (needs a running web app): just shots docs/design/qc/phase-1 / /drills
shots out +paths:
    node scripts/screenshots.mjs {{out}} {{paths}}

# Everything CI runs locally (except the e2e and the service smoke).
check: lint types test test-web eol-check gen-check colors-check fmt-web-check
