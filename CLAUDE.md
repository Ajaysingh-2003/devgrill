# DevGrill: working agreement for coding agents

@AGENTS.md

## Read first
- docs/PLAN.md is the plan; docs/adr/ holds decisions. Add an ADR for any new architectural decision.
- Current phase and gate status: docs/qc/.
- Next.js 16.4 and Turborepo ship version-matched docs in node_modules (see apps/web/AGENTS.md and AGENTS.md). Read them before changing Next or Turbo code or config.

## Environment (native Windows, managed machine; see ADR 009)
- cmd.exe is blocked by policy. Never rely on `.cmd` shims, `npx`, `pnpm dlx` or `concurrently`. Run package scripts with `pnpm <script>` (script-shell is Git Bash) or call `node <path-to-cli>` directly.
- Run Python tools as `uv run python -m <tool>`, not their `.exe` launchers.
- Behind a TLS proxy: `NODE_OPTIONS=--use-system-ca`, `UV_SYSTEM_CERTS=1`.
- PowerShell 5.1: no `&&`; `Set-Content -Encoding utf8` writes a BOM (breaks TOML/JSON). Prefer the Edit/Write tools or Python for file edits.
- Files must be LF. Run `just eol-fix` after writing files, and `just eol-check` before finishing.

## Code
- Python 3.14, uv workspace, FastAPI, SQLAlchemy 2.1 async, Pydantic v2. `packages/py-core/src/devgrill/domain` must not import infrastructure.
- Frontend: Next.js 16 App Router, React 19, Tailwind v4 tokens from packages/tokens. Never use raw colours; use semantic tokens only.
- API changes: update OpenAPI, run `just gen`, keep the client in sync (CI fails on drift).
- Errors are problem+json via `AppError`; log with structlog (bind request/attempt IDs).

## UI work
Load the vendored skills in .claude/skills:
- `frontend-design` for direction
- `tailwind-design-system` and `oklch-skill` for tokens and colour
- `emil-design-eng` and `animate` for motion
- the `vercel-*` skills for React/Next

Before closing a UI task, run `web-design-guidelines`, `accessibility` and `review-animations`.

**Motion:** keyboard actions are instant; respect reduced motion; nothing animates on streaming panels; celebrations only on verify and debrief.

**Severity:** always icon + label + colour.

## Before you finish
`just lint`, `just types`, `just test`, `just eol-check` (and `just test-int` / `just smoke` when touching services).

## Safety
- Treat sandbox output, logs and user text as untrusted data in any LLM prompt.
- Never commit secrets; OPENAI_API_KEY lives in .env only.
