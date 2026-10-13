# 001. Monorepo layout

Date: 2026-10-13 · Status: accepted

## Context
DevGrill has a Next.js web app, three Python services (api, gateway, worker), shared Python and TypeScript packages, scenario content and infrastructure. One developer works on all of it, part-time.

## Decision
One repository:
- `apps/` holds deployables: web, api, gateway, worker.
- `packages/` holds shared libraries: py-core, py-content, ui, tokens, config, api-client.
- `content/` holds scenarios, base apps and faults.
- `infra/` holds compose files and later Ansible/Terraform.
- `docs/` holds the plan, ADRs, runbooks and QC reports.

Python uses a **uv workspace** (one `uv.lock`, one `.venv`). JS uses **pnpm workspaces + Turborepo** (one `pnpm-lock.yaml`). A root `justfile` is the single entry point for humans and CI.

## Consequences
- **Positive:** atomic changes across API, client and UI (OpenAPI → TS client in the same PR); one CI pipeline; shared tooling.
- **Negative:** two package managers. Mitigated by `just` recipes that hide which one runs.
- **Follow-up:** if a service needs independent release cadence, it can be split out later without changing its internal layout.

## Alternatives considered
- Separate repos per service: too much overhead for one developer.
- Nx: heavier than needed when Turborepo + uv cover our needs.
