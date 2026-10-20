# DevGrill — Development Plan

> **Name:** DevGrill (formerly "IncidentGym"). *Get grilled before prod does.*
> **What it is:** a flight simulator for on-call. Engineers get paged, investigate a **live, broken multi-service system** in a browser workspace, mitigate, fix the root cause, pass a **verify** step that replays traffic and runs chaos probes, and write a postmortem that is graded by AI.
> **Plan date:** 2026-10-12 · **Owner:** solo developer, part-time (15–20 hrs/week) · **Status:** pre-scaffold
> **Owner decisions (2026-10-12):** name DevGrill · everything runs **locally** for now (hosting and cost decided later) · develop on **native Windows** · **closed source** · **India-first** (IST rollover) · **GitHub sign-in** only for now · pricing decided later. See §21.

---

## Table of contents

0. [How to read this plan](#0-how-to-read-this-plan)
1. [Product vision, users and principles](#1-product-vision-users-and-principles)
2. [Name decision](#2-name-decision)
3. [Market position](#3-market-position)
4. [System architecture](#4-system-architecture)
5. [Tech stack (pinned versions)](#5-tech-stack-pinned-versions)
6. [Repository layout](#6-repository-layout)
7. [Design system: brand, palette, type, motion](#7-design-system)
8. [UX architecture: screens, templates, flows, retention](#8-ux-architecture)
9. [Data model](#9-data-model)
10. [API design](#10-api-design)
11. [Scenario engine and content system](#11-scenario-engine-and-content-system)
12. [Sandbox infrastructure](#12-sandbox-infrastructure)
13. [AI system](#13-ai-system)
14. [Quality framework (applies to every phase)](#14-quality-framework)
15. [Phased roadmap with QC gates (+ Track H: hosting, deferred)](#15-phased-roadmap)
16. [Scalability and long-term architecture](#16-scalability-and-long-term-architecture)
17. [Security, privacy and abuse](#17-security-privacy-and-abuse)
18. [Metrics and analytics](#18-metrics-and-analytics)
19. [Business model (draft, deferred)](#19-business-model-draft-deferred)
20. [Risks and mitigations](#20-risks-and-mitigations)
21. [Owner decisions and remaining open items](#21-owner-decisions-and-remaining-open-items)
22. [Appendices](#22-appendices)

---

## 0. How to read this plan

- **Sections 1–13 are the design**: what we build and why. **Section 15 is the build order**: phases, tasks, deliverables and the QC gate that closes each phase.
- Every phase ends with a **QC gate**. A phase is not done until every item in its gate is checked. Section 14 defines the gates shared by every phase, and each phase adds its own.
- Versions in section 5 were checked on 2026-10-12. **Pin exact versions** and update them deliberately. Several key libraries are still 0.x (FastAPI, the OpenAI Agents SDK, Hey API).
- Durations assume **15–20 hrs/week**. "1 week" means about 17 focused hours.
- Architecture decisions are recorded as ADRs in `docs/adr/` (template in Appendix F). When this plan and an ADR disagree, the newer ADR wins.

---

## 1. Product vision, users and principles

### 1.1 Problem

Engineers learn incident response on the job, at 2 a.m., on real customers. LeetCode-style practice covers algorithms, not debugging distributed systems under pressure. Existing tools split the problem in two:

- **Real infrastructure, no incident framing:** SadServers, iximiuz Labs.
- **Incident framing, no live debugging:** Uptime Labs, Rootly Academy, and simulated-terminal games.

### 1.2 What DevGrill is

A scenario library organised like a DSA sheet (tracks → topics → scenarios). In each scenario you:

1. **Get paged.** A briefing, a pager alert and a story.
2. **Investigate** a real sandboxed stack: API, worker, Postgres, Valkey/Redis and a load generator. You have a terminal, logs, metrics, a code editor, deploys and a war room with AI teammates.
3. **Mitigate.** Roll back, flip a flag or shed load. This is scored on time.
4. **Fix the root cause** in real code.
5. **Verify.** The platform attacks your fix: traffic replay, chaos probes, correctness tests and budget constraints. **It grades behaviour, not code**, so any fix that holds passes.
6. **Write a postmortem.** AI grades it against a rubric.
7. **Debrief.** See your rating change, how your fix compares with every other approach players tried, and a replay of your investigation with time-loss markers.

### 1.3 Target users

| Segment | Need | How they find us |
|---|---|---|
| Early-career engineers, 0–4 years (India first, then global) | Production skills that interviews and on-call rotations demand | LinkedIn and X share cards, college communities, Daily Incident |
| Mid and senior engineers | Sharpen skills, try new failure domains, mentor others | HN and Reddit, weekly outage replays of real postmortems |
| Interview candidates (SRE, backend, platform) | Practice for "debug this" rounds | SEO, Quick Fire |
| Later: teams, bootcamps, colleges | Cohort training, hiring signals | Cohorts and B2B |

### 1.4 Product principles

1. **Real systems, real tools.** No simulated terminals in the core loop.
2. **Grade behaviour, not code.** Many fixes are valid. Show the trade-offs.
3. **Calm under pressure.** The UI is a control room, not a casino. Gamification is opt-in loudness.
4. **Time to first win under 5 minutes.** Guest mode, a tutorial incident, and no signup wall before the first win.
5. **Every scenario is code.** It is versioned, validated by CI, and checked to break and to be fixable before it ships.
6. **Long-term substrate independence.** Scenarios don't know what runs them: Docker today, Sysbox for the beta, Firecracker at scale.
7. **AI is a teammate, not an oracle.** It gives hints, it doesn't solve. AI never takes actions in a user's sandbox.

### 1.5 Non-goals (for the first 12 months)

- Kubernetes-based scenarios (they need heavier sandboxes; planned for phase 10+).
- Native mobile apps. Mobile web Quick Fire covers phones.
- Hiring and assessment products. The design keeps the door open.
- Real-time multiplayer before the single-player loop is excellent.

---

## 2. Name decision

**Decision (owner, 2026-10-12): DevGrill.** Getting *grilled* is the pressure engineers practise for: the 2 a.m. page, the war room, the "debug this" interview round. "Dev" keeps it broad: backend, platform and SRE, not only SREs. It is short, easy to say in Indian and US English, and reads as practice under fire rather than a puzzle sheet.

**Conflict check (2026-10-12):**
- No software product, company or open-source project named DevGrill was found. The nearest name is DevGrid, a UK software agency: different spelling, different business.
- `devgrill.com` and `devgrill.dev` are **unregistered** (registry RDAP returned 404).
- `.io`, `.gg` and `.app` have no DNS records, so they appear free (unverified).
- The GitHub handle `devgrill` is free.

Alternatives considered: SevDrill (the earlier recommendation), Postmortal, Smokejumper. Rejected for conflicts: Sev0 (incident.io's conference), Firedrill (FireHydrant feature), Drillbit (Indian plagiarism tool), Redline, Hotwash.

**Before going public** (not needed while everything is local):
- [ ] Register `devgrill.com` and `devgrill.dev` (cheap insurance even before launch).
- [ ] Claim GitHub, X and LinkedIn handles.
- [ ] Run a trademark search (USPTO and IP India, classes 9, 41 and 42).

**Tagline candidates:** "Get grilled before prod does." · "Your first Sev1 shouldn't be your first Sev1." · "On-call reps, without the 2 a.m."

The name lives in one config constant (`packages/config/brand.ts` and `apps/api/.../settings.py`), so renaming before launch is cheap.

**Voice:** dry, precise, a little playful. For example "You've been paged." · "Sev1 survived." · "MTTR personal best." Never cutesy during an incident.

---

## 3. Market position

| Competitor | Strength | Gap DevGrill fills |
|---|---|---|
| SadServers | Real VMs, ~100 Linux scenarios, $9–11/mo | Single box with a script check. No multi-service stack, dashboards, load-replay verify or incident narrative |
| iximiuz Labs | Best-in-class Firecracker infra, 150+ challenges, cheap | Teaches Linux, containers and K8s, not incident response under time pressure |
| Killercoda / KodeKloud | Certification labs | Tutorials, not incidents |
| Uptime Labs / Rootly Academy | Incident drills, AI stakeholders, coordination | No hands-on live-system debugging |
| YouBrokeProd, The Incident Challenge | Incident framing | Mostly simulated environments |

**Open space:** a real live stack, observability, injected faults, automated load-replay and chaos verification, AI mentoring, scoring that accepts multiple valid solutions, and a skill-rating system, all in one product.

**Moat over time:**
1. The scenario library and its validation pipeline.
2. The approach dataset ("how 10,000 engineers fixed this").
3. Calibrated ratings.
4. Community-contributed postmortem replays.

---

## 4. System architecture

### 4.1 Context (MVP → beta)

```mermaid
flowchart LR
  subgraph Browser
    WEB[Next.js app<br/>RSC + client islands]
  end
  subgraph ControlPlane[Control plane]
    API[FastAPI api<br/>REST + SSE]
    GW[Sandbox gateway<br/>WebSocket PTY + telemetry mux]
    TW[Temporal workers<br/>sandbox lifecycle, verify, AI jobs]
    TMP[(Temporal server)]
    PG[(Postgres 18 + pgvector)]
    VK[(Valkey 9)]
    S3[(SeaweedFS / S3<br/>recordings, artifacts)]
    LF[Langfuse<br/>LLM traces + evals]
  end
  subgraph SandboxHost[Sandbox host]
    DRV[SandboxDriver<br/>compose → sysbox → firecracker]
    SB1[Session sandbox<br/>api · worker · pg · redis · toxiproxy · exporters]
    VER[Verifier<br/>k6 + probes, outside the sandbox]
  end
  OAI[OpenAI Responses API]

  WEB -- HTTPS JSON --> API
  WEB -- WSS terminal / SSE telemetry --> GW
  API --> PG & VK
  API -- start workflows --> TMP
  TW --> TMP
  TW --> DRV
  GW --> DRV
  DRV --> SB1
  VER --> SB1
  TW --> VER
  TW --> OAI
  API --> OAI
  API & TW --> LF
  TW --> S3
```

### 4.2 Services

| Service | Language | Responsibility | Scales by |
|---|---|---|---|
| `web` | Next.js 16 / React 19 | UI, Better Auth (sessions, OAuth), BFF route handlers, OG/share images | Stateless; Vercel or container |
| `api` | Python 3.14, FastAPI | Domain API: catalog, attempts, progress, ratings, AI chat endpoints, admin | Stateless; horizontal |
| `gateway` | Python (FastAPI WS), moving to Go if p99 latency requires it | Authenticated WebSocket terminal (PTY), file read/write and deploy commands into sandboxes, telemetry fan-out | Per sandbox host, sticky by session |
| `worker` | Python, Temporal SDK | Workflows: `SandboxLifecycle`, `VerifyRun`, `GradePostmortem`, `ClassifyApproach`, `GenerateScenario`; activities call drivers and OpenAI | Temporal task queues per concern |
| `content-cli` | Python (Typer) | Validate, build, run, test and publish scenarios from `content/` | CI + local |
| Datastores | Postgres 18 (+pgvector), Valkey 9, SeaweedFS→S3, Temporal (on Postgres) | | See §16 |

### 4.3 Key flows

**Start an attempt**

1. `POST /v1/attempts` creates an `attempt` row (`state=provisioning`).
2. It starts the Temporal workflow `SandboxLifecycle(attempt_id)` and returns `202`.
3. The workflow runs: `provision` (driver.create) → `wait_healthy` → `inject_faults` → `start_load_profile` → set state `active` → start TTL timer.
4. The browser polls or subscribes over SSE (`/v1/attempts/{id}/events`). When the state is `active`, it requests a short-lived WS ticket and connects to the gateway.
5. Signals during the session: `extend`, `reset`, `verify_requested`, `abandon`. On TTL, idle or done, the workflow runs `snapshot_artifacts` → `destroy`. Teardown is guaranteed, which is the main reason we use Temporal.

**Verify**

1. `POST /v1/attempts/{id}/verify` starts `VerifyRun`. The verifier runs **outside** the sandbox on the sandbox network, so a root user can't fake the checks.
2. It runs the probes listed in `scenario.yaml` in order: load replay (k6 thresholds), chaos (Toxiproxy toxics, key deletion, service restart), invariants (SQL and HTTP assertions), hidden tests, and the resource budget.
3. It writes `verify_runs` and `probe_results`, triggers `ClassifyApproach`, and the debrief becomes available.

**Mentor and war room**

1. `POST /v1/attempts/{id}/messages` stores the message.
2. The API builds context: scenario persona prompts, the hint ladder, the redacted investigation trail and the latest telemetry summary.
3. It streams the response from the OpenAI Responses API over SSE.
4. Scripted "beats" (time-based or state-based teammate messages) are emitted by the workflow, not the LLM, so pacing stays deterministic.

### 4.4 Architectural rules

- **Ports and adapters.** The domain code (`devgrill.domain`) imports no FastAPI, SQLAlchemy, Docker or OpenAI. Adapters live in `devgrill.infra.*`.
- **Every external dependency sits behind an interface:** `SandboxDriver`, `LLMClient`, `ObjectStore`, `Clock`, `EventBus`. Tests use fakes.
- **Idempotency.** Every mutating endpoint accepts `Idempotency-Key`, and every Temporal activity is idempotent.
- **One writer per table.** For example, only the lifecycle workflow writes `sandbox_sessions.state`.
- **Time is UTC, IDs are UUIDv7.** Postgres 18 has native `uuidv7()`, which sorts by time and is index-friendly.

---

## 5. Tech stack (pinned versions)

> Checked 2026-10-12. Python versions are from PyPI. JS versions are from an npm mirror, because the corporate proxy blocks registry.npmjs.org, so re-check JS versions when you install. **Pin exactly** in lockfiles.

### 5.1 Backend

| Area | Choice | Version | Why |
|---|---|---|---|
| Runtime | Python | **3.14** (pin `.python-version` = `3.14`; uv 0.13 otherwise defaults to 3.15) | Current stable; wheels available for every dependency below |
| Project manager | uv (workspace) | 0.13.0 | One lockfile across `apps/api`, `apps/worker` and `packages/py-*` |
| Web | FastAPI on Starlette | 0.143.0 / 1.7.0 | Async, typed, generates OpenAPI |
| Server | uvicorn (granian later) | 0.54.0 | uvloop is unavailable on Windows; asyncio is fine for dev |
| Validation / settings | Pydantic v2, pydantic-settings | 2.14.1 / 2.15.0 | |
| ORM | SQLAlchemy 2.1 (async) | 2.1.4 | Plain declarative models, not SQLModel |
| Driver | asyncpg | 0.32.0 | |
| Migrations | Alembic (async template) | 1.20.0 | |
| Workflows / jobs | **Temporal** (`temporalio`), CLI dev server | SDK 1.34.0, CLI 1.9.1 | Durable sandbox lifecycle: timers, signals, guaranteed teardown. Short jobs are also activities, so there is only one job system |
| Cache / pub-sub / rate limits | **Valkey** | `valkey/valkey:9.1` | BSD licence, a drop-in for Redis; use the `redis` 8.1.0 Python client |
| Docker control | aiodocker | 0.27.0 | Compose driver, exec PTY, logs |
| SSE | sse-starlette | 3.5.0 | Telemetry and LLM streaming |
| Auth verification | PyJWT[crypto] | 2.15.1 | Verifies Better Auth JWTs against JWKS |
| Rate limiting | limits (Valkey storage) | 5.8.0 | |
| Logging / tracing | structlog; OpenTelemetry SDK + instrumentations | 26.1.0; 1.45.1 / 0.66b1 | |
| LLM | `openai` (Responses API), `openai-agents` | 3.29.0 / 0.23.1 | Structured outputs via `responses.parse` |
| LLM observability | Langfuse (self-hosted, phase 6+) | server 4.56.0, SDK 4.17.0 | Traces, prompt versions, datasets, evals |
| Load / chaos (inside the verifier) | k6, Toxiproxy, stress-ng | latest stable at phase 3 | |
| Tests | pytest, pytest-asyncio, testcontainers, Schemathesis, pytest-xdist, polyfactory | 9.1.1, 1.4.0, 4.15.0, 4.31.0, 3.8.0, 3.3.0 | |
| Lint / types | ruff; basedpyright as the CI gate (ty is optional and not gating) | 0.17.0; 1.40.2 | |

### 5.2 Data

| Store | Image / version | Use |
|---|---|---|
| Postgres | `pgvector/pgvector:0.8.7-pg18-trixie` (Postgres 18.6) | System of record; `uuidv7()`; pgvector for approach and scenario embeddings |
| Valkey | `valkey/valkey:9.1` | Sessions cache, rate limits, pub/sub fan-out, leaderboards (sorted sets) |
| Object storage | SeaweedFS S3 API (local; MinIO no longer publishes images) → S3 or R2 | Terminal recordings (asciicast), diffs, verify artifacts, share images |
| Temporal | CLI dev server locally; Postgres-backed in prod | |
| Later | ClickHouse `26.8` | Events, telemetry, analytics; Langfuse needs it anyway |

### 5.3 Frontend

| Area | Choice | Version | Why |
|---|---|---|---|
| Framework | Next.js 16 (App Router, Turbopack) + React 19 | 16.4.0 / 19.3.0 | Stable View Transitions; `"use cache"` opt-in caching. Apply the Oct 8 security update |
| Language | TypeScript, **pinned `~6`** | 6.x | TS 7 (Go-native) is not yet confirmed with Next 16.4 or typescript-eslint |
| CSS | Tailwind CSS v4 (CSS-first `@theme`) | 4.3.3 | OKLCH tokens natively |
| Components | shadcn/ui CLI on **Base UI** | shadcn 4.21.4, @base-ui/react 1.9.0 | We own the component code; accessible primitives |
| Motion | `motion` (`motion/react`) + CSS + View Transitions | 14.1.0 | |
| Command palette | cmdk | latest | ⌘K |
| Panels | react-resizable-panels | latest | WAI-ARIA window splitter, persisted layouts |
| Terminal | @xterm/xterm + addon-fit, addon-attach, addon-webgl | 6.0.0 / 0.11.0 / 0.12.0 | Client-only; v6 removed the canvas renderer |
| Editor | CodeMirror 6 via @uiw/react-codemirror | 6.43.x / 4.25.12 | Small bundle, works on mobile; Monaco remains the alternative |
| Charts | uPlot (realtime), ECharts (rich static) | 1.6.32 / 6.1.0 | uPlot handles high-frequency streams cheaply |
| Virtualised lists | @tanstack/react-virtual | latest | Log viewer |
| Data | TanStack Query v5, Zustand, react-hook-form + zod v4 | 5.104.2, 5.0.15, 7.90.0 + 4.6.7 | |
| API client | @hey-api/openapi-ts (fetch + TanStack Query + zod plugins) | 0.99.0 (pin exactly) | Generated from FastAPI OpenAPI |
| Auth | **Better Auth** (+ JWT plugin, **GitHub OAuth**; Google and email can be added later with config only) | 1.7.7 | Stores data in our Postgres (`auth` schema); FastAPI verifies JWTs via JWKS |
| Toasts | sonner | latest | Out-of-world confirmations only |
| Icons | lucide-react + custom SEV glyph set | latest | |
| Tests | Vitest, Playwright, @axe-core/playwright, Storybook 10 | 5.0.4, 1.64.0, —, 10.6.1 | |
| Monorepo | pnpm workspaces + Turborepo | pnpm 12.11.2, turbo 2.11.7 | |
| Lint / format | ESLint 10 + typescript-eslint, Prettier (or Biome 2.5, decided in an ADR during phase 0) | | |

### 5.4 Infrastructure and tooling

| Area | Choice |
|---|---|
| Local (owner decision: **native Windows**) | Windows 11 + Docker Desktop 29 (Linux containers on its WSL2 engine, used only as Docker's backend), PowerShell or Git Bash, VS Code. All app code runs natively on Windows; all datastores and scenario sandboxes run in Docker |
| CI | GitHub Actions: lint, types, unit, integration (testcontainers), contract (Schemathesis), e2e (Playwright), a11y (axe), Lighthouse CI, image scan (Trivy), secrets scan (gitleaks), dependency audit (pip-audit, pnpm audit) |
| Hosting (**deferred**: owner decision to stay local for now) | Options kept open for later: 1× dedicated Linux sandbox host (Hetzner or OVH, 64 GB, Sysbox) + a small control-plane VM, **or** hosted sandboxes (Modal/Fly) pay-per-use. Decide in the Hosting track (§15, H) |
| Product analytics | PostHog (cloud free tier, or self-hosted later) |
| Errors | Sentry (free tier) for web and api |
| Email | Mailpit locally (digest and notification testing); a provider such as Resend only when hosted |

### 5.5 Windows and corporate-network setup notes

- The corporate proxy (Cisco Umbrella) intercepts TLS. Point Node and Python at the corporate root CA:
  - `NODE_EXTRA_CA_CERTS=<path-to-corp-root.pem>`
  - `SSL_CERT_FILE=<same>`
  - `UV_SYSTEM_CERTS=1` for uv (`UV_NATIVE_TLS` is deprecated)
  - Add `--ssl-no-revoke` for curl.
- Install `uv` (standalone installer) and `pnpm` (`npm i -g pnpm@12`). Neither is installed yet.
- Prefer a personal or non-proxied network for heavy image pulls if the proxy throttles Docker Hub.

**Native-Windows rules (owner decision):**

| Topic | Rule |
|---|---|
| Line endings | `.gitattributes` with `* text=auto eol=lf`. Scenario scripts, Dockerfiles and shell files **must** be LF, or containers fail with `\r` errors. Set `git config core.autocrlf false` |
| Shell | Task runner is **`just`** (install via `winget install Casey.Just`), configured with `set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]`. GNU make is not used. Scripts that run inside containers are bash; scripts that run on the host are Python (via `uv run`), never bash or PowerShell, so they work everywhere |
| Paths | `pathlib` in Python and `node:path` in JS. Never hard-code `/` or `\` |
| Python | uvicorn without uvloop (asyncio loop). Temporal Python SDK and asyncpg ship Windows wheels for 3.14 |
| Temporal | Use the Temporal CLI dev server in Docker (Appendix B), so there's no Windows-binary dependency |
| Docker | Docker Desktop with the WSL2 engine. Give it ≥ 8 GB RAM and 4 CPUs (Settings → Resources) so 2–3 scenario stacks can run at once. Datastores and sandboxes are containers; app code runs natively |
| Docker API access | The ComposeDriver talks to the Docker Engine through `aiodocker`. On Windows it uses the named pipe `npipe:////./pipe/docker_engine`; set `DOCKER_HOST` explicitly if needed and cover it with an integration test |
| File watching | Next.js and uvicorn reload run natively, so there are no bind-mount slowdowns. Avoid bind-mounting the repo into containers for hot reload |
| Ports | Reserve 3000 (web), 8000 (api), 8100 (gateway), 5432, 6379, 7233/8233, 9000/9001, 8025. Check with `netstat -ano` if a port is taken by a Windows service |
| CI | GitHub Actions on **Linux** runners, which catches Windows-only assumptions early. Add one Windows job for the Python unit suite |

---

## 6. Repository layout

A single monorepo: pnpm/Turborepo for the JS side and a uv workspace for the Python side, coordinated by a top-level `justfile` (`just` runs natively on Windows).

```
devgrill/
├─ apps/
│  ├─ web/                     # Next.js 16 (App Router)
│  │  ├─ app/
│  │  │  ├─ (marketing)/       # landing, pricing, blog
│  │  │  ├─ (auth)/            # sign-in, callback
│  │  │  ├─ (app)/             # authenticated shell: library, track, profile, settings
│  │  │  ├─ (incident)/        # briefing, workspace, debrief (full-bleed layouts)
│  │  │  ├─ (quickfire)/       # mobile-first Quick Fire
│  │  │  ├─ admin/             # content console (role-gated)
│  │  │  └─ api/auth/[...all]/ # Better Auth handler
│  │  ├─ components/           # app-specific composites
│  │  ├─ features/             # feature slices: workspace/, library/, debrief/ …
│  │  ├─ lib/                  # auth client, api client wiring, telemetry
│  │  └─ styles/               # globals.css imports @devgrill/tokens
│  ├─ api/                     # FastAPI service (uv project)
│  │  └─ src/devgrill_api/
│  │     ├─ main.py            # app factory, routers, middleware
│  │     ├─ routers/           # v1 routers per resource
│  │     ├─ schemas/           # Pydantic request/response models
│  │     ├─ deps.py            # auth, db session, rate limit deps
│  │     └─ settings.py
│  ├─ gateway/                 # WS terminal + telemetry mux (uv project)
│  └─ worker/                  # Temporal workers (uv project)
├─ packages/
│  ├─ py-core/                 # devgrill.domain (pure), devgrill.infra (db, drivers, llm, storage)
│  ├─ py-content/              # scenario spec models + content CLI (Typer)
│  ├─ ui/                      # shadcn-generated + custom components, Storybook
│  ├─ tokens/                  # design tokens: tokens.json → CSS variables + TS
│  ├─ api-client/              # generated by @hey-api/openapi-ts (do not edit)
│  └─ config/                  # eslint, tsconfig, tailwind preset, brand constants
├─ content/
│  ├─ base-apps/               # shopkart/, shortly/, chatter/, ledger/ (Dockerfiles, compose fragments)
│  ├─ faults/                  # reusable fault modules (patches, toxics, scripts)
│  ├─ scenarios/<track>/<slug>/ # scenario.yaml, inject/, verify/, hints.md, solution/, rubric.yaml
│  ├─ quickfire/               # card decks (yaml)
│  └─ schemas/                 # JSON Schema for scenario.yaml (generated from Pydantic)
├─ infra/
│  ├─ compose/                 # docker-compose.dev.yml (platform deps), .observability.yml, .langfuse.yml
│  ├─ docker/                  # Dockerfiles for api, gateway, worker, web
│  ├─ sandbox-host/            # Sysbox host provisioning (Ansible), nftables rules
│  └─ terraform/               # later
├─ docs/
│  ├─ adr/                     # architecture decision records
│  ├─ runbooks/                # our OWN on-call runbooks (eat the dog food)
│  └─ design/                  # design-system notes, screenshots, QC reports
├─ .claude/skills/             # vendored design, UX and motion skills (see VENDORED.md)
├─ CLAUDE.md                   # agent working agreement for this repo (Appendix E)
├─ justfile                   # cross-platform task runner (works natively on Windows)
├─ pnpm-workspace.yaml · turbo.json · package.json
└─ pyproject.toml              # uv workspace root
```

---

## 7. Design system

### 7.1 Direction: "Control Room × Field Manual"

The product deliberately avoids the LeetCode and HackerRank look (cool charcoal, orange or green accents, Easy/Medium/Hard traffic-light tables). It also avoids the 2025–26 SaaS default (near-black with indigo/purple glow gradients).

| Layer | Where | Feel |
|---|---|---|
| **Control Room** (default) | Workspace, library, profile, admin | Warm graphite neutrals, dense data typography, mono metadata, one cool **Signal** accent. Calm under pressure. Light mode is a first-class "daylight ops" theme, not an afterthought |
| **Field Manual** (editorial) | Briefings, postmortems, debriefs, landing, blog | Paper off-white light mode, **serif display headlines**, mono margin notes. Signals SRE and blameless-postmortem culture |
| **Pager Arcade** (loud, contained) | Share cards, streak and season screens, Quick Fire, marketing hero | Bold grotesk, chunky 2px borders, **Volt** and **Flare** pops. **Never inside the incident workspace** |

**Brand-colour rule:** red, amber and green are reserved for severity and health semantics. The brand is **Signal cyan**, which reads as telemetry and collides with no semantic colour, and is not LeetCode orange, HackerRank green or SaaS indigo.

### 7.2 Colour (OKLCH, contrast-validated)

All values were generated in OKLCH with sRGB gamut clamping (generator: `packages/tokens/src/build.ts`, which also fails the build on any contrast miss). **Every text and background pair below passes WCAG AA (4.5:1)** in both themes. Hex values are fallbacks and for tooling only. Source of truth: `packages/tokens/tokens.json` → CSS variables.

#### 7.2.1 Primitive scales

| Step | **graphite** (neutral, H75) | **signal** (brand, H210) | **flare** (H352) | **volt** (H124) | **red** (H25) | **orange** (H50) | **amber** (H78) | **green** (H152) |
|---|---|---|---|---|---|---|---|---|
| 50 | `oklch(0.975 0.005 75)` #f9f6f3 | `oklch(0.975 0.007 210)` #f2f8f9 | `oklch(0.975 0.004 352)` #f9f6f7 | `oklch(0.975 0.018 124)` #f4f9ec | `oklch(0.975 0.003 25)` #f9f6f6 | `oklch(0.975 0.004 50)` #f9f6f4 | `oklch(0.975 0.006 78)` #f9f6f2 | `oklch(0.975 0.01 152)` #f2f9f3 |
| 100 | `oklch(0.945 0.005 75)` #efece9 | `oklch(0.945 0.025 210)` #dbf2f6 | `oklch(0.945 0.014 352)` #f5e9ee | `oklch(0.945 0.071 124)` #e3f6c2 | `oklch(0.945 0.012 25)` #f5eae9 | `oklch(0.945 0.014 50)` #f5eae5 | `oklch(0.945 0.022 78)` #f5ebdd | `oklch(0.945 0.038 152)` #dbf5e1 |
| 200 | `oklch(0.895 0.009 75)` #e0dcd6 | `oklch(0.895 0.087 210)` #95edfc | `oklch(0.895 0.052 352)` #f9cfe0 | `oklch(0.895 0.178 124)` #c4f05e | `oklch(0.895 0.045 25)` #f9d2cd | `oklch(0.895 0.05 50)` #f9d4bf | `oklch(0.895 0.077 78)` #f9d7a3 | `oklch(0.895 0.143 152)` #8ef8ad |
| 300 | `oklch(0.825 0.009 75)` #c9c5bf | `oklch(0.825 0.131 210)` #3adcf4 | `oklch(0.825 0.093 352)` #f5adcc | `oklch(0.825 0.164 124)` #b0d753 | `oklch(0.825 0.08 25)` #f6b2ac | `oklch(0.825 0.089 50)` #f5b592 | `oklch(0.825 0.134 78)` #f5ba57 | `oklch(0.825 0.165 152)` #64e48f |
| 400 | `oklch(0.735 0.009 75)` #ada8a3 | `oklch(0.735 0.117 210)` #30bdd2 | `oklch(0.735 0.156 352)` #f27cb3 | `oklch(0.735 0.146 124)` #96b846 | `oklch(0.735 0.133 25)` #f1867e | `oklch(0.735 0.146 50)` #f18b4d | `oklch(0.735 0.126 78)` #d59e41 | `oklch(0.735 0.147 152)` #55c37a |
| 500 | `oklch(0.645 0.009 75)` #918d88 | `oklch(0.645 0.103 210)` #269eb0 | `oklch(0.645 0.219 352)` #e9409b | `oklch(0.645 0.128 124)` #7e9a3a | `oklch(0.645 0.197 25)` #ee4d4c | `oklch(0.645 0.14 50)` #d07135 | `oklch(0.645 0.11 78)` #b28536 | `oklch(0.645 0.129 152)` #46a465 |
| 600 | `oklch(0.56 0.009 75)` #78746f | `oklch(0.56 0.089 210)` #1e8291 | `oklch(0.56 0.19 352)` #c13480 | `oklch(0.56 0.111 124)` #677f2e | `oklch(0.56 0.186 25)` #cb3637 | `oklch(0.56 0.121 50)` #ac5c2a | `oklch(0.56 0.096 78)` #936d2a | `oklch(0.56 0.112 152)` #388753 |
| 700 | `oklch(0.475 0.009 75)` #5f5c57 | `oklch(0.475 0.076 210)` #156874 | `oklch(0.475 0.162 352)` #9b2766 | `oklch(0.475 0.094 124)` #516523 | `oklch(0.475 0.158 25)` #a2292a | `oklch(0.475 0.103 50)` #894820 | `oklch(0.475 0.081 78)` #755620 | `oklch(0.475 0.095 152)` #2b6b41 |
| 800 | `oklch(0.395 0.009 75)` #494641 | `oklch(0.395 0.063 210)` #0e4f59 | `oklch(0.395 0.134 352)` #781c4e | `oklch(0.395 0.079 124)` #3e4d18 | `oklch(0.395 0.131 25)` #7e1e1f | `oklch(0.395 0.086 50)` #6a3716 | `oklch(0.395 0.068 78)` #5a4116 | `oklch(0.395 0.079 152)` #205230 |
| 900 | `oklch(0.315 0.009 75)` #34312d | `oklch(0.315 0.05 210)` #083840 | `oklch(0.315 0.107 352)` #571237 | `oklch(0.315 0.063 124)` #2b370f | `oklch(0.315 0.105 25)` #5c1314 | `oklch(0.315 0.069 50)` #4d260d | `oklch(0.315 0.054 78)` #412e0d | `oklch(0.315 0.063 152)` #143b21 |
| 950 | `oklch(0.24 0.009 75)` #221f1b | `oklch(0.24 0.027 210)` #0f2326 | `oklch(0.24 0.057 352)` #331222 | `oklch(0.24 0.034 124)` #1c220f | `oklch(0.24 0.056 25)` #351311 | `oklch(0.24 0.037 50)` #2d1a0f | `oklch(0.24 0.029 78)` #271e0f | `oklch(0.24 0.034 152)` #122417 |

Dark-mode surfaces (deeper than graphite-950, warm, not blue-black):

| Token | OKLCH | Hex |
|---|---|---|
| dark-canvas | `oklch(0.17 0.006 70)` | #110f0d |
| dark-surface | `oklch(0.2 0.007 70)` | #181613 |
| dark-raised | `oklch(0.235 0.008 70)` | #211d1a |
| dark-border | `oklch(0.3 0.009 70)` | #312d29 |
| dark-border-strong | `oklch(0.38 0.01 70)` | (generate from tokens) |

#### 7.2.2 Semantic tokens (what components use)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--canvas` | `oklch(0.985 0.005 85)` #fcfaf6 (paper) | `oklch(0.17 0.006 70)` #110f0d | Page background |
| `--surface` | `oklch(1 0 0)` #fff | `oklch(0.2 0.007 70)` #181613 | Cards, panels |
| `--raised` | graphite-100 #efece9 | `oklch(0.235 0.008 70)` #211d1a | Hover, inputs, nested panels |
| `--border` | graphite-200 #e0dcd6 | `oklch(0.3 0.009 70)` #312d29 | Hairlines |
| `--border-strong` | graphite-300 | `oklch(0.38 0.01 70)` | Focused containers, dividers |
| `--text` | graphite-950 #221f1b | graphite-50 #f9f6f3 | Body |
| `--text-muted` | graphite-700 #5f5c57 | graphite-300 #c9c5bf | Secondary |
| `--text-subtle` | `oklch(0.52 0.009 75)` | graphite-400 #ada8a3 | Captions, timestamps (≥4.5:1 on raised) |
| `--brand` | `oklch(0.52 0.098 215)` #00768c | `oklch(0.8 0.12 205)` #44d4e2 | Primary buttons, focus, active nav |
| `--on-brand` | #fff | graphite-950 | Text on brand fills |
| `--brand-text` | signal-700 #156874 | signal-300 #3adcf4 | Links, brand-coloured text |
| `--flare` / `--flare-text` | flare-600 / flare-700 | flare-400 / flare-300 | Streaks, celebration, "new" (Arcade layer) |
| `--volt` / `--on-volt` | volt-300 / graphite-950 | volt-300 / graphite-950 | Rating up, XP, personal best (Arcade layer) |
| `--danger-text` / `--danger-solid` | red-700 / red-600 | red-300 / red-500 | Errors, SEV1, failing probes |
| `--warning-text` | amber-800 | amber-300 | Warnings, SEV3, partial credit |
| `--success-text` / `--success-solid` | green-700 / green-700 | green-300 / green-500 | Healthy, passed, resolved |
| `--info-text` | signal-700 | signal-300 | Info notes (info shares the brand hue) |
| `--focus-ring` | `--brand` | `--brand` | 2px ring, 2px offset |

**Validated contrast (selected):**

| Pair | Light | Dark |
|---|---|---|
| text / canvas | 15.8:1 | 17.8:1 |
| text-muted / surface | 6.7:1 | 10.5:1 |
| text-subtle / raised | 4.5:1 | 7.1:1 |
| brand-text / surface | 6.5:1 | 11.0:1 |
| on-brand / brand | 5.3:1 | 9.2:1 |
| danger-text / surface | 7.3:1 | 10.2:1 |
| warning-text / surface | 9.5:1 | 10.4:1 |
| success-text / surface | 6.4:1 | 11.2:1 |

#### 7.2.3 Severity system (difficulty *and* in-scenario alerts)

Severity is never shown by colour alone. It is always **glyph + label + colour** (WCAG 1.4.1).

| Level | Glyph | Light badge (fg on bg) | Dark badge | Contrast L / D |
|---|---|---|---|---|
| SEV1 · critical | ◆◆◆◆ | red-700 on red-100 | red-300 on red-950 | 6.2 / 9.5 |
| SEV2 · major | ◆◆◆◇ | orange-700 on orange-100 | orange-300 on orange-950 | 5.9 / 9.4 |
| SEV3 · minor | ◆◆◇◇ | amber-800 on amber-100 | amber-300 on amber-950 | 8.1 / 9.5 |
| SEV4 · warm-up | ◆◇◇◇ | signal-700 on signal-100 | signal-300 on signal-950 | 5.6 / 9.7 |

Scenario **difficulty** uses the same ladder: SEV4 is warm-up and SEV1 is hardest. This replaces "Easy/Medium/Hard" and gives the library its own identity.

#### 7.2.4 Chart palette (categorical, equal lightness)

| Series | Light (L 0.56, on white) | Dark (L 0.76, on dark-surface) |
|---|---|---|
| 1 signal | `oklch(0.56 0.078 210)` #32818e | `oklch(0.76 0.105 210)` #51c3d6 |
| 2 violet | `oklch(0.56 0.231 300)` #8d42e4 | `oklch(0.76 0.116 300)` #bca0f0 |
| 3 volt | `oklch(0.56 0.121 130)` #5c822e | `oklch(0.76 0.164 130)` #8ec54a |
| 4 flare | `oklch(0.56 0.186 352)` #bf3680 | `oklch(0.76 0.134 352)` #f18cba |
| 5 amber | `oklch(0.56 0.093 80)` #916e2d | `oklch(0.76 0.126 80)` #dba749 |
| 6 blue | `oklch(0.56 0.166 258)` #2d71d3 | `oklch(0.76 0.099 258)` #8ab3f0 |
| 7 orange | `oklch(0.56 0.128 45)` #b0582d | `oklch(0.76 0.122 45)` #f1976e |
| 8 teal | `oklch(0.56 0.087 172)` #33856f | `oklch(0.76 0.118 172)` #52c9a8 |

All series are ≥4.4:1 against the panel (chart marks need 3:1).

**Chart rules:**
- SLO and threshold lines are dashed `--text-subtle`.
- Deploy and sale markers are dotted vertical rules with mono labels.
- Breach regions get a 10%-alpha danger fill.
- Use **tabular numerals** everywhere.
- **New data snaps; it never re-tweens.**

#### 7.2.5 Theming implementation

- Use DevGrill's own `ThemeProvider` (ADR 010; replaces the planned `next-themes`) with a `class` on `<html>`, defaulting to **system**. Users can override per device, and the setting is stored on the profile.
- `packages/tokens` emits:
  - `tokens.css`: `:root { … }` plus `.dark { … }` semantic variables.
  - A Tailwind v4 `@theme inline` block that maps `--color-canvas: var(--canvas)` and so on, so utilities like `bg-surface text-muted border-border` work in both themes.
- Optional later: a **high-contrast** theme (raise text L, use solid borders) and a **colour-blind-safe severity** theme (blue/orange swap), following Linear's base + accent + contrast approach.
- Wrap P3-boosted brand colours in `@media (color-gamut: p3)`, with the sRGB value as the default.

```css
/* packages/tokens/dist/tokens.css (excerpt) */
:root {
  --canvas: oklch(0.985 0.005 85);
  --surface: oklch(1 0 0);
  --text: oklch(0.24 0.009 75);
  --brand: oklch(0.52 0.098 215);
  --on-brand: oklch(1 0 0);
  /* … */
}
.dark {
  --canvas: oklch(0.17 0.006 70);
  --surface: oklch(0.2 0.007 70);
  --text: oklch(0.975 0.005 75);
  --brand: oklch(0.8 0.12 205);
  --on-brand: oklch(0.24 0.009 75);
  /* … */
}
@theme inline {
  --color-canvas: var(--canvas);
  --color-surface: var(--surface);
  --color-fg: var(--text);
  --color-brand: var(--brand);
  --color-on-brand: var(--on-brand);
}
```

### 7.3 Typography

| Role | Typeface | Licence / source | Why |
|---|---|---|---|
| UI sans | **Instrument Sans** (variable, with a width axis) | OFL · Google Fonts (`next/font/google`) | Crisp, slightly condensed, not Inter or Geist (avoids looking like Vercel or Linear) |
| Editorial display | **Instrument Serif** (+ italic) | OFL · Google Fonts | Field Manual headlines: debrief titles, postmortems, landing |
| Code / data | **JetBrains Mono** | OFL · Google Fonts | Terminal, logs, IDs, timestamps, metrics; ligatures **off** in the terminal |
| Arcade display | **Bricolage Grotesque** | OFL · Google Fonts | Share cards, streak screens, Quick Fire, marketing only |
| Indic fallback (roadmap) | Noto Sans Devanagari / IBM Plex Sans Devanagari | OFL | Hindi UI later |

Avoid: Satoshi and General Sans (Fontshare licence restricts redistribution), Berkeley Mono (paid), Space Grotesk (dated), Inter and Geist as primary faces (generic or brand-coded).

**Type scale** (rem, 16px root; UI default is 14px):

| Token | Size / line height | Font | Use |
|---|---|---|---|
| `display-2xl` | 60/64, -0.02em | Instrument Serif | Landing hero |
| `display-xl` | 44/48, -0.015em | Instrument Serif | Debrief headline, page heroes |
| `display-lg` | 32/38 | Instrument Serif | Briefing title |
| `heading-lg` | 24/32, 600 | Instrument Sans | Section titles |
| `heading-md` | 18/26, 600 | Instrument Sans | Panel and card titles |
| `body-lg` | 16/26 | Instrument Sans | Briefings, postmortems (65–75ch measure) |
| `body` | 14/22 | Instrument Sans | Default UI |
| `label` | 13/18, 500 | Instrument Sans | Buttons, inputs |
| `caption` | 12/16 | Instrument Sans | Metadata |
| `mono` | 13/20 | JetBrains Mono | Code, logs, terminal (terminal 13–14px is user-adjustable) |
| `mono-sm` | 12/16, +0.02em, uppercase optional | JetBrains Mono | Eyebrows, IDs, timestamps |
| `stat` | 28/32, 600, tabular | JetBrains Mono | KPI tiles, MTTR, ratings |

**Rules:**
- `font-variant-numeric: tabular-nums` on every number that updates.
- Sentence case everywhere.
- No all-caps text over 3 words.
- Serif never appears inside the incident workspace.

### 7.4 Space, shape, elevation, layout

- **Spacing:** 4px base (`1 = 4px`). Common values: 4, 8, 12, 16, 20, 24, 32, 40, 56, 80. Dense workspace panels use 8/12; reading surfaces use 24/32.
- **Radius:**
  - `xs` 4 (badges, kbd)
  - `sm` 6 (inputs, buttons)
  - `md` 10 (cards, panels)
  - `lg` 14 (dialogs, sheets)
  - `full` (avatars, pills)

  Arcade layer only: 0 radius with 2px borders.
- **Borders over shadows.** 1px hairlines (`--border`) do most of the work. Shadows are reserved for floating layers (popover, dialog, command palette): one soft shadow in light mode, and an inner highlight plus darker backdrop in dark mode.
- **Z-index scale:** base 0, sticky 10, panel-overlay 20, dropdown 30, sheet 40, dialog 50, palette 60, toast 70.
- **Breakpoints:** `sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536. **The workspace requires ≥1024px.** Below that, the app routes to the mobile experience (§8.6).
- **Content widths:** reading 720px, app pages 1200px, workspace full-bleed.

### 7.5 Motion

**Principles** (from emil-design-eng, apple-design, Material 3 and WCAG 2.3.3):
- Motion communicates state; it never decorates.
- Most UI motion stays under 300ms, with ease-out for responses.
- **Keyboard-initiated actions are instant.**
- Animate only `transform` and `opacity`, and make every animation interruptible.

| Token | Duration | Easing | Use |
|---|---|---|---|
| `instant` | 0ms | — | Keyboard-triggered palette and preset switches, panel resize (direct manipulation), log lines, terminal output |
| `fast` | 120ms | `cubic-bezier(0.2, 0, 0, 1)` | Hover, press, tab switch, focus ring |
| `base-in` / `base-out` | 200ms / 150ms | in `cubic-bezier(0.05, 0.7, 0.1, 1)`, out `cubic-bezier(0.23, 1, 0.32, 1)` (ease-out: exits never ease in) | Popovers, dropdowns, sheets, mouse-initiated collapse |
| `slow` | 320ms | emphasized-decelerate | Route transitions (View Transitions API), opening the debrief |
| `celebrate` | 600–1000ms sequence | spring (motion) | **Only on verify-passed and the debrief**: checkmark draw → rating delta count-up → skill bars fill. Skippable with a click or keypress |

**Incident-specific rules:**
- An alert arriving appears in the timeline instantly, plus a tab badge (the timeline is a streaming surface, so it doesn't animate).
- No looping pulses or shakes. Anything moving for more than 5s needs a pause control (WCAG 2.2.2).
- No skeleton shimmer on streaming panels.
- No confetti during an incident.
- Respect `prefers-reduced-motion`: replace movement with opacity, and turn off count-ups and springs.
- Also provide an in-app **Reduce motion** toggle in settings.
- Lint rule: no CSS transition without a `@media (prefers-reduced-motion)` path (enforced with a stylelint plugin or a code-review checklist).

### 7.6 Iconography and illustration

- **Icons:** lucide-react, 1.5px stroke, 16/20px sizes, plus a custom SEV glyph set and service icons (api, worker, db, cache, queue, lb), drawn on the same grid.
- **Illustration:** schematic line art in the style of service maps and runbook diagrams. Mono labels, signal-colour highlights. No 3D blobs and no stock illustration.
- **Sounds (optional, off by default):** a short pager chirp on page and a soft chime on resolve, with an accessibility-signal toggle (VS Code model).

### 7.7 Component inventory

Base components come from shadcn/ui on Base UI: Button, Input, Textarea, Select, Combobox, Checkbox, Switch, Radio, Tabs, Dialog, Sheet, Popover, Tooltip, DropdownMenu, ContextMenu, Toast (sonner), Avatar, Badge, Kbd, Separator, ScrollArea, Skeleton, Progress, Accordion, Breadcrumb, Pagination, Table, Form.

Custom components (in `packages/ui`, each with a Storybook story covering light, dark, reduced-motion and every state):

| Component | Notes |
|---|---|
| `AppShell` | Top bar, ⌘K trigger, theme toggle, profile; `(incident)` routes use a different shell |
| `CommandPalette` | cmdk. Fuzzy search, recent commands first, shortcut hints, context-aware commands in the workspace |
| `WorkspaceLayout` | react-resizable-panels, layout presets, persisted per user, focus mode (maximise a panel) |
| `ToolRail` | Vertical tool switcher; alert badges; keyboard 1–7 |
| `Terminal` | xterm.js (WebGL addon), reconnect with backoff, `tmux`-backed session restore, screen-reader mode, copy-on-select, font-size control |
| `LogViewer` | Virtualised; structured fields; level filter; query bar; pause-on-hover; "N new lines ↓" pill; freeze key |
| `MetricChart` | uPlot wrapper with SLO lines, markers, crosshair sync across charts, tabular legend |
| `CodeEditor` + `DiffView` | CodeMirror 6, file tree, dirty-state, deploy button |
| `DeployList` | Deploy history, rollback action, flag toggles |
| `WarRoom` | Chat with persona avatars, streaming replies, hint cards, @mention teammates |
| `IncidentTimeline` | Persistent in-world event feed: alerts, beats, user actions. **In-world events never become toasts** |
| `SevBadge`, `StatusPill`, `ProbeRow`, `ApproachCard`, `RatingDelta`, `MasteryRing`, `StreakFlame`, `ShareCard`, `EmptyState`, `BootSequence` (sandbox provisioning narrative) | |

---

## 8. UX architecture

### 8.1 Sitemap

```
/                          Landing (Field Manual + Arcade hero) → "Take a 5-min incident" (guest)
/try                       Guest tutorial incident (no signup)
/sign-in                   GitHub (Google / email can be added later)
/onboarding                Role + experience → optional 6-card triage calibration (skippable)
/drills                    Library: tracks as runbook chapters / service map
/drills/[track]            Track: topics → scenario cards, mastery, primers
/drills/[track]/[slug]     Scenario briefing
/incident/[attemptId]      Workspace (full-bleed)
/incident/[attemptId]/postmortem
/incident/[attemptId]/debrief
/daily                     Today's incident (one global scenario, spoiler-free share)
/weekly                    Weekly outage (real-postmortem replay)
/quickfire                 Mobile-first triage cards (3 strikes, 3/5-min runs)
/u/[handle]                Public profile: per-track ratings, solved, postmortems (opt-in public)
/cohorts, /cohorts/[id]    Private leagues (college / company / bootcamp)
/settings                  Theme, reduce motion, sounds, gamification ("Pro mode" hides XP/streaks), privacy
/admin/*                   Content console (role-gated)
```

### 8.2 Page templates (built in phase 1 as static shells and filled in later)

| Template | Layer | Key regions |
|---|---|---|
| T1 Marketing | Field Manual + Arcade | Hero with a live mini-incident replay, how-it-works, track map, social proof, pricing, footer |
| T2 App page | Control Room | Top bar, page header (eyebrow + title + actions), content grid, right rail optional |
| T3 Library / Track | Control Room | **Service-map hero** (tracks as nodes with mastery rings), topic sections, scenario cards (SEV glyph, est. time, solve rate, status), filter chips, "list view" toggle for power users |
| T4 Briefing | Field Manual | Serif title, story, system diagram, goals, grading promise ("there is no single right answer"), mode picker, Start |
| T5 Workspace | Control Room, dense | Incident bar (SEV, title, clock, hints, verify) · phase stepper · tool rail · resizable panels · war room + timeline |
| T6 Debrief | Field Manual + Arcade moment | Result hero, probe table, approach comparison, postmortem review, investigation replay, next drills |
| T7 Postmortem editor | Field Manual | Template sections, timeline auto-inserted from the trail, live rubric hints, submit |
| T8 Quick Fire | Arcade, mobile | Card stack, 3 strikes, timer, swipe answers, end card with share |
| T9 Profile | Control Room | Ratings per track (with history sparkline), heatmap of activity, postmortems |
| T10 Admin | Control Room, dense | Tables, review queue, scenario analytics, validation reports |
| T11 System | Control Room | 404, 500, maintenance, sandbox-capacity queue ("You're #3 — about 40s") |

### 8.3 Core flows

1. **First run (guest), aiming for a win in under 5 minutes.**
   1. Landing → "Take a 5-min incident".
   2. `/try` starts a SEV4 tutorial scenario. Only Terminal and Logs are unlocked. The IC teammate gives just-in-time tips, each once and dismissible.
   3. One obvious signal (an OOM in the logs). The fix is a single command. Verify passes.
   4. A short celebration, then a mini debrief.
   5. *"Save your rating and streak"* leads to sign-up. Sign-up is delayed on purpose; Duolingo saw about +20% DAU from this.
2. **Core loop:** Library → Briefing → Workspace (triage → investigate → mitigate → fix) → Verify → Postmortem → Debrief → next drill. The phase stepper shows exactly where the user is.
3. **Daily Incident.** One 10–15 min scenario for everyone, the same day worldwide (rolls over at 00:00 IST, with a UTC option). Spoiler-free share card, for example `SEV2 · resolved 11:42 · 1 hint · ◆◆◇◇`.
4. **Weekly Outage.** A longer multi-service replay of a real public postmortem, with a weekly goal and private-cohort boards.
5. **Quick Fire (mobile).** Read a log, graph or diff and pick the cause or next command. 3 strikes. Counts toward the streak and has its own rating.

### 8.4 Workspace UX spec

**Panels and progressive disclosure:**
- Tutorial 1 unlocks Terminal and Logs.
- Tutorial 2 adds Metrics.
- Tutorial 3 adds Code, Deploys and the War Room.
- After that, the full workspace and layout presets. Unlocking panels doubles as progression.

**Layout presets (⌘/Ctrl + 1..4):**

| Preset | Layout |
|---|---|
| Triage | Metrics and Logs large |
| Debug | Terminal and Code |
| Comms | War Room and Timeline |
| Postmortem | Editor with a read-only timeline |

**Focus mode:** `F` maximises the focused panel; `Esc` restores it.

**Keyboard map:**

| Key | Action |
|---|---|
| ⌘K | Command palette |
| `?` | Shortcut sheet |
| `1–7` | Tools |
| F6 / Shift+F6 | Cycle panel focus |
| `/` | Filter logs |
| `.` | Freeze log stream |
| ⌘⏎ | Deploy (in the editor) |
| ⌘⇧V | Verify |
| `H` | Request hint |
| `M` | Declare mitigated |

**Command palette verbs:** Go to panel · Run suggested command · Filter logs by… · Compare keys · Roll back… · Toggle flag… · Declare mitigated · Ask teammate… · Request hint · Verify · Switch preset · Theme.

**Notifications:**
- In-world events (alerts, teammate beats) go to the **Incident Timeline** and a tab badge.
- An `aria-live="assertive"` announcement is used only for a genuine page. Everything else is `polite`.
- Toasts (sonner) are for out-of-world confirmations only ("Layout saved").

**Clock:** visible by default in On-call mode, hideable in Guided mode, and never shown on the debrief as pressure.

**Resilience:**
- The terminal reconnects automatically and resumes the session through tmux.
- Losing the network shows a banner and never blanks the panels.
- Sandbox expiry warnings appear at T-5 min and T-1 min, with **Extend** (a quota-limited signal).

**Sandbox boot:** the `BootSequence` component narrates real progress: *Allocating sandbox · Pulling ShopKart · Seeding 18k products · Injecting fault · Starting sale traffic*. It shows real states from workflow events and never fakes a progress bar.

**Empty states:** every panel explains why it is empty and what to do next. For example, Metrics: *"No alerts firing yet. Alerts appear here when SLOs breach."*

### 8.5 Retention mechanics, with guardrails

| Mechanic | Implementation | Guardrail |
|---|---|---|
| Daily Incident (Wordle model) | One global scenario per day plus a spoiler-free share grid | Short (10–15 min); no penalty for skipping |
| Per-track rating (Lichess model) | Glicko-2 per track; attempt = match vs the scenario's rating; hints and Guided mode reduce gains (like Lichess themed puzzles) | Ratings are private by default; public profile is opt-in |
| Streaks | Daily *or* weekly streak (the user picks). Any Quick Fire run counts (Brilliant's low bar). 2 earnable freezes. "On-call leave" days | Never sell freezes. No guilt copy. Max 1 notification/day with quiet hours. One-tap pause |
| Weekly Outage | Weekly goal (e.g. 2 incidents/week) suits working engineers | |
| Leagues | **Opt-in private cohorts** (college, company), per-scenario "segments" (fastest MTTR among friends) | No global speed leaderboard (Advent of Code removed theirs over stress and AI speed-running) |
| Approach comparison | "38% of solvers used coalescing" | Shown only after you solve the scenario (no spoilers) |
| Share cards | OG images for result, rating milestones, postmortem excerpt (opt-in) | No PII; spoiler-free |
| Pro mode | Hides XP, streaks and leagues for seniors (answers the Boot.dev criticism) | |
| Mentoring | AI postmortem review by default; human senior review later (community or paid) | |

### 8.6 Responsive strategy

- **Desktop at 1024px and up:** full workspace.
- **Tablet:** workspace with 2 panels and tabs for the rest.
- **Phone (<768px):** the workspace is **not** shrunk. Phones get:
  - Quick Fire
  - Daily briefing
  - Debrief and postmortem reading
  - War-room replay
  - Profile
  - "Continue on laptop" (QR code or one-time handoff link)

  India's web traffic is about two-thirds mobile and Android-heavy, so mobile routes must be light: route-level code splitting, subset variable fonts, no xterm, CodeMirror or uPlot on mobile routes.

### 8.7 Accessibility requirements (WCAG 2.2 AA)

- All interactive elements are reachable and operable by keyboard with a visible focus ring.
- Splitters follow the WAI-ARIA Window Splitter pattern (`role="separator"`, arrow keys resize, Enter collapses).
- Severity and status always combine icon + text + colour.
- Text contrast ≥ 4.5:1 (validated in §7.2); UI marks ≥ 3:1.
- Terminal screen-reader mode, plus an **Accessible View** (Alt+F2) that shows terminal, log and chat output as a navigable text buffer.
- Live regions as specified in §8.4. Panel titles are real headings.
- Reduced motion is respected (OS setting + in-app toggle); nothing autoplays for more than 5s without a pause control.
- Forms use real labels, error text linked via `aria-describedby`, and never rely on placeholders alone.
- Automated checks: axe on every Playwright e2e page. Manual checks: NVDA (Windows) on the core loop once per phase from phase 4 onward.

### 8.8 Which vendored skill to use, and when

| When | Skill (`.claude/skills/`) |
|---|---|
| Setting aesthetic direction, a new page or template | `frontend-design` |
| Tokens, Tailwind v4 `@theme`, variants (CVA) | `tailwind-design-system`, `oklch-skill` |
| Any colour change; contrast fixes | `oklch-skill` |
| Building or tuning an animation | `animate`, `emil-design-eng`, `apple-design` (springs, gestures) |
| Animation jank | `animation-performance` |
| End-of-phase motion QC | `review-animations` |
| End-of-phase UI QC | `web-design-guidelines` (vendored rules), `accessibility` |
| React and Next performance; component APIs; route transitions | `vercel-react-best-practices`, `vercel-composition-patterns`, `vercel-react-view-transitions` |
| Core Web Vitals regressions | `core-web-vitals` |

---

## 9. Data model

Postgres 18. Two schemas:
- **`auth`**, owned by Better Auth: user, session, account, verification, jwks.
- **`app`**, owned by Alembic: everything else.

Domain tables reference `auth.user.id`. Keys are `uuid` with default `uuidv7()`, except high-volume event tables, which use `bigint identity`. Timestamps are `timestamptz` (UTC). Soft deletes only where noted. JSONB columns are always validated by Pydantic before writes.

### 9.1 Entity-relationship overview

```mermaid
erDiagram
  AUTH_USER ||--|| PROFILE : has
  TRACK ||--o{ TOPIC : contains
  TOPIC ||--o{ SCENARIO : groups
  BASE_APP ||--o{ SCENARIO_VERSION : runs_on
  SCENARIO ||--o{ SCENARIO_VERSION : versions
  SCENARIO_VERSION ||--o{ SCENARIO_FAULT : injects
  FAULT ||--o{ SCENARIO_FAULT : used_by
  SCENARIO_VERSION ||--o{ PROBE : verifies_with
  SCENARIO_VERSION ||--o{ HINT : has
  SCENARIO ||--o{ APPROACH : known_fixes
  AUTH_USER ||--o{ ATTEMPT : makes
  SCENARIO_VERSION ||--o{ ATTEMPT : played_as
  ATTEMPT ||--o{ SANDBOX_SESSION : runs_in
  ATTEMPT ||--o{ ATTEMPT_EVENT : records
  ATTEMPT ||--o{ WAR_ROOM_MESSAGE : chats
  ATTEMPT ||--o{ VERIFY_RUN : verifies
  VERIFY_RUN ||--o{ PROBE_RESULT : yields
  ATTEMPT ||--o| POSTMORTEM : writes
  POSTMORTEM ||--o{ POSTMORTEM_GRADE : graded_by
  AUTH_USER ||--o{ SKILL_RATING : per_track
  AUTH_USER ||--o| STREAK : keeps
  CHALLENGE ||--o{ CHALLENGE_ENTRY : entries
  COHORT ||--o{ COHORT_MEMBER : members
```

### 9.2 Tables

**Identity and profile**

| Table | Key columns | Notes |
|---|---|---|
| `profiles` | `user_id` PK (Better Auth's user id; no cross-schema FK, ADR 011), `handle` unique citext, `display_name`, `avatar_url`, `country`, `experience_level` enum(student, 0-2, 2-5, 5+), `roles` text[] (user, author, reviewer, admin), `prefs` jsonb (theme, reduce_motion, sounds, pro_mode, streak_mode daily/weekly, tz, notification settings), `is_public` bool, `created_at` | Created on first login (Better Auth hook → `POST /internal/profiles`) |
| `entitlements` | `user_id`, `plan` enum(free, pro, team), `limits` jsonb (concurrent_sandboxes, daily_minutes, ai_msgs_per_day), `valid_until` | Phase 9+ billing; free defaults until then |

**Catalog and content**

| Table | Key columns | Notes |
|---|---|---|
| `tracks` | `id`, `slug` unique, `title`, `summary`, `icon`, `position`, `status` | Databases, Caching, Queues, Concurrency, Memory & CPU, Networking, Deploys & config, Distributed |
| `topics` | `id`, `track_id`, `slug`, `title`, `primer_md`, `position` | |
| `base_apps` | `id`, `slug` (shopkart…), `name`, `version`, `services` jsonb, `image_digests` jsonb | Built and published by content-cli |
| `faults` | `id`, `slug` (db/missing-index…), `kind` enum(code_patch, config, toxic, resource, data, infra), `params_schema` jsonb, `version` | |
| `scenarios` | `id`, `slug` unique, `track_id`, `topic_id`, `title`, `summary`, `difficulty` enum(sev4..sev1), `est_minutes`, `status` enum(draft, review, published, retired), `source` enum(handwritten, generated, community, postmortem_replay), `current_version_id`, `tags` text[], **Glicko fields** `rating`, `rd`, `vol`, `created_by` | Scenario rating is calibrated from attempts |
| `scenario_versions` | `id`, `scenario_id`, `version` int, `spec` jsonb (validated `scenario.yaml`), `content_hash`, `base_app_id`, `validation_report` jsonb, `solver_report` jsonb, `published_at` | Immutable once published; attempts pin a version |
| `scenario_faults` | `scenario_version_id`, `fault_id`, `params` jsonb | |
| `probes` | `id`, `scenario_version_id`, `key`, `kind` enum(load, chaos, invariant, hidden_test, budget), `config` jsonb, `target` jsonb, `weight` | |
| `hints` | `scenario_version_id`, `tier` 1–3, `body_md` | |
| `rubrics` | `scenario_version_id`, `criteria` jsonb (`[{key, max, description, anchors}]`) | Postmortem grading |
| `approaches` | `id`, `scenario_id`, `key`, `name`, `outcome` enum(full, partial, fails), `idea_md`, `exemplar_patch`, `pros`, `cons`, `embedding` vector(1536), `discovered_from_attempt_id` | Grows from classification + review |
| `quickfire_cards` | `id`, `track_id`, `kind` enum(log, graph, diff, config), `prompt` jsonb, `options` jsonb, `answer`, `explanation_md`, Glicko fields | |

**Play**

| Table | Key columns | Notes |
|---|---|---|
| `attempts` | `id`, `user_id` (nullable for guests; claimed on sign-up), `guest_token_hash`, `scenario_version_id`, `mode` enum(tutorial, guided, oncall, daily, weekly), `state` enum(provisioning, active, mitigated, verifying, resolved, abandoned, expired, failed), `started_at`, `active_at`, `mitigated_at`, `resolved_at`, `ended_at`, `hints_used`, `score` jsonb, `rating_delta` jsonb, `approach_id`, `approach_confidence`, `workflow_id` | One active attempt per user (partial unique index) |
| `sandbox_sessions` | `id`, `attempt_id`, `driver` enum(compose, sysbox, firecracker, hosted), `host`, `external_ref`, `state`, `resources` jsonb, `created_at`, `ready_at`, `expires_at`, `destroyed_at`, `cpu_seconds`, `est_cost_usd` | Cost tracking from day one |
| `attempt_events` | `id` bigint identity, `attempt_id`, `ts`, `type` (tool_open, command, query, hint, message, deploy, rollback, flag, verify_start, verify_end, beat, alert, state_change), `payload` jsonb | Investigation trail; monthly partitions in phase 8; ClickHouse in phase 10 |
| `recordings` | `attempt_id`, `kind` (terminal_asciicast, code_diff), `object_key`, `bytes` | S3 (SeaweedFS locally) |
| `code_changes` | `id`, `attempt_id`, `diff`, `files` text[], `deployed_at`, `deploy_ok` | |
| `war_room_messages` | `id`, `attempt_id`, `author_kind` enum(user, persona, system), `persona_key`, `body`, `ts`, `llm_call_id` | |
| `verify_runs` | `id`, `attempt_id`, `code_change_id`, `status` enum(queued, running, passed, partial, failed, error), `started_at`, `finished_at`, `summary` jsonb | |
| `probe_results` | `verify_run_id`, `probe_id`, `passed`, `observed` jsonb, `artifact_key` | |
| `postmortems` | `id`, `attempt_id` unique, `body_md`, `submitted_at`, `is_public` | |
| `postmortem_grades` | `id`, `postmortem_id`, `judge_model`, `judge_prompt_version`, `scores` jsonb, `total`, `feedback_md`, `created_at` | Multiple graders allowed (calibration) |

**Progression and social**

| Table | Key columns | Notes |
|---|---|---|
| `skill_ratings` | `user_id`, `track_id` (PK pair), `rating`, `rd`, `vol`, `games`, `updated_at` | Glicko-2; separate row for Quick Fire (`track_id` = quickfire pseudo-track) |
| `rating_history` | `user_id`, `track_id`, `attempt_id`, `before`, `after`, `ts` | |
| `activity_days` | `user_id`, `day` date, `kinds` text[] | Streak source of truth |
| `streaks` | `user_id`, `mode`, `current`, `longest`, `freezes`, `last_day` | Derived; recomputable |
| `achievements`, `user_achievements` | | Small, phase 9 |
| `challenges` | `id`, `kind` enum(daily, weekly), `scenario_version_id`, `starts_at`, `ends_at` | |
| `challenge_entries` | `challenge_id`, `user_id`, `attempt_id`, `result` jsonb | |
| `cohorts`, `cohort_members` | invite codes, roles | Private leagues |

**Platform and operations**

| Table | Notes |
|---|---|
| `llm_calls` | `feature`, `model`, `prompt_version`, `input_tokens`, `cached_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `attempt_id`, `user_id`, `trace_id`, `status`. Budget enforcement and cost dashboards |
| `generation_jobs` | AI scenario generation: `input`, `status`, `scenario_version_id`, `solver_report`, `cost_usd` |
| `content_reviews` | `scenario_version_id`, `reviewer_id`, `decision`, `notes` |
| `feature_flags` | `key`, `enabled`, `rules` jsonb (simple; swap for OpenFeature or PostHog flags later) |
| `audit_log` | `actor_id`, `action`, `target`, `data`, `ts`. Admin and content actions |
| `idempotency_keys` | Kept in Valkey (24 h TTL), not a table (ADR 011) |

### 9.3 Indexes, constraints and data rules

- `attempts`:
  - `(user_id, started_at desc)`
  - partial unique `(user_id) where state in ('provisioning','active','mitigated','verifying')` (one live attempt per user)
- `attempt_events (attempt_id, ts)`
- `scenarios (track_id, status, difficulty)`
- GIN on `scenarios.tags`
- HNSW on `approaches.embedding vector_cosine_ops`
- Every foreign key has an index. Check constraints on enums are mirrored in Pydantic.
- **Migrations** go forward only in production. Each migration is reviewed against a "safe migration" checklist: no long locks, add columns nullable then backfill, create indexes `CONCURRENTLY`. This is the same class of bug the Databases track teaches, so we follow it too.
- **Retention:**
  - `attempt_events` and recordings: 180 days for free users, longer for paid.
  - LLM prompts and completions in Langfuse: 30 days.
  - Postmortems: kept while the account exists.

---

## 10. API design

### 10.1 Conventions

- **Versioning and format:** REST under `/v1`, JSON, snake_case on the wire. The generated TS client maps to camelCase.
- **Auth:**
  - Browser to Next.js uses Better Auth session cookies.
  - Next (server components and route handlers) to FastAPI uses `Authorization: Bearer <Better Auth JWT>` (EdDSA). FastAPI verifies it against cached JWKS.
  - WebSocket and SSE to the gateway use a **single-use ticket** (`POST /v1/attempts/{id}/ws-ticket`, 60s TTL, bound to the attempt and user).
- **Errors:** RFC 9457 `application/problem+json`, with `type`, `title`, `status`, `detail`, `code` and `errors[]` for validation.
- **Pagination:** cursor-based (`?cursor=&limit=`), returning `next_cursor`.
- **Idempotency:** `Idempotency-Key` header on POSTs that create resources or start workflows.
- **Rate limits:** per user and per IP, in Valkey. Headers follow the `RateLimit` / `RateLimit-Policy` IETF draft. Strict buckets for `attempts.create`, `verify`, `messages` and `hints`.
- **Long operations** return `202 Accepted` with a resource URL. Progress arrives over SSE (`/events`).
- **OpenAPI** is the contract. CI runs Schemathesis against it, and `packages/api-client` is regenerated on every API change (CI fails on drift).

### 10.2 Endpoints

**Catalog (public, cacheable)**

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/tracks` | Tracks with counts (+ my mastery if authenticated) |
| GET | `/v1/tracks/{slug}` | Topics + scenario cards |
| GET | `/v1/scenarios` | Filter: `track, topic, difficulty, status=published, q, cursor` |
| GET | `/v1/scenarios/{slug}` | Briefing payload (story, system diagram, goals, modes) — no solution data |
| GET | `/v1/scenarios/{slug}/approaches` | **Only if the caller has resolved it** (403 otherwise) |
| GET | `/v1/challenges/daily`, `/v1/challenges/weekly` | Current challenges |

**Me and progress**

| Method | Path | Purpose |
|---|---|---|
| GET / PATCH | `/v1/me` | Profile + prefs |
| GET | `/v1/me/ratings` | Per-track Glicko + history |
| GET | `/v1/me/progress` | Solved, attempted, mastery per topic |
| GET | `/v1/me/streak` | Streak, freezes, activity heatmap |
| GET | `/v1/me/attempts` | History (cursor) |
| POST | `/v1/me/claim-guest` | Attach guest attempts after sign-up |

**Attempts (core loop)**

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/attempts` | `{scenario_slug, mode}` → 202 `{id, state}`; starts `SandboxLifecycle`. Errors: `409 active_attempt_exists`, `429 quota_exceeded`, `503 capacity` (+ queue position) |
| GET | `/v1/attempts/{id}` | State, timers, unlocked panels, phase |
| GET | `/v1/attempts/{id}/events` | **SSE**: state changes, alerts, teammate beats, verify progress |
| POST | `/v1/attempts/{id}/ws-ticket` | Gateway ticket |
| POST | `/v1/attempts/{id}/extend` | Extend TTL (quota) |
| POST | `/v1/attempts/{id}/reset` | Reset sandbox to the initial broken state |
| DELETE | `/v1/attempts/{id}` | Abandon |
| GET | `/v1/attempts/{id}/files?path=` / PUT | Read or write source files in the sandbox (via gateway) |
| POST | `/v1/attempts/{id}/deploys` | Deploy the current working tree → 202 |
| POST | `/v1/attempts/{id}/rollbacks` | `{to_version}` |
| POST | `/v1/attempts/{id}/flags` | `{key, value}` (scenario-defined flags) |
| POST | `/v1/attempts/{id}/mitigation` | Declare mitigated (scored against real recovery) |
| POST | `/v1/attempts/{id}/hints` | Next hint tier (or LLM nudge in Guided) |
| GET / POST | `/v1/attempts/{id}/messages` | War room; POST streams the persona reply (SSE) |
| GET | `/v1/attempts/{id}/telemetry?from=&to=` | Historical metrics/logs window (live data via gateway) |
| POST | `/v1/attempts/{id}/verify` | Start `VerifyRun` → 202 |
| GET | `/v1/attempts/{id}/verify-runs/{run_id}` | Probe results |
| PUT | `/v1/attempts/{id}/postmortem` | Save draft |
| POST | `/v1/attempts/{id}/postmortem/submit` | Triggers grading |
| GET | `/v1/attempts/{id}/debrief` | Score, probes, approach, comparisons, replay, rating delta |
| GET | `/v1/attempts/{id}/replay` | Investigation trail + recording keys (signed URLs) |

**Gateway (separate host, ticket-authenticated)**

| Protocol | Path | Purpose |
|---|---|---|
| WSS | `/gw/v1/sessions/{attempt_id}/terminal` | Binary PTY frames; control messages `resize`, `ping` |
| WSS | `/gw/v1/sessions/{attempt_id}/telemetry` | Multiplexed: `metrics` (1–2s samples), `logs` (lines), `alerts` |

**Quick Fire, social and challenges**

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/quickfire/runs` | Start a run (`length=3m/5m`) → first card |
| POST | `/v1/quickfire/runs/{id}/answers` | Answer → next card / end summary |
| GET / POST | `/v1/cohorts`, `/v1/cohorts/{id}`, `/v1/cohorts/{id}/join` | Private leagues |
| GET | `/v1/leaderboards` | `scope=cohort|scenario_segment&id=` |
| GET | `/v1/share/{kind}/{id}` | Share metadata (images rendered by Next `ImageResponse`) |

**Admin and content (role: author / reviewer / admin)**

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/admin/scenarios` | All statuses, validation state |
| POST | `/v1/admin/scenario-versions/{id}/validate` | Run full validation pipeline (break → fix → solver) |
| POST | `/v1/admin/scenario-versions/{id}/publish` · `/retire` | |
| GET / POST | `/v1/admin/reviews` | Review queue, decisions |
| GET | `/v1/admin/analytics/scenarios` | Solve rate, median time, hint usage, drop-off step, rating drift |
| GET / POST | `/v1/admin/approaches` | Review "unknown approach" clusters, promote to known |
| GET / POST | `/v1/admin/generation-jobs` | AI scenario generation (phase 10) |
| GET | `/v1/admin/llm/costs` | Spend by feature, model, day |

**Internal and operations:** `GET /healthz`, `GET /readyz` (DB, Valkey, Temporal), `POST /internal/profiles` (Better Auth hook, HMAC-signed).

### 10.3 Example: start an attempt

```http
POST /v1/attempts
Authorization: Bearer eyJ...
Idempotency-Key: 7f9c…
Content-Type: application/json

{ "scenario_slug": "big-sale-meltdown", "mode": "guided" }
```

```json
HTTP/1.1 202 Accepted
Location: /v1/attempts/0199e6c2-…

{
  "id": "0199e6c2-…",
  "state": "provisioning",
  "scenario": { "slug": "big-sale-meltdown", "version": 3 },
  "events_url": "/v1/attempts/0199e6c2-…/events",
  "expires_at": null
}
```

---

## 11. Scenario engine and content system

### 11.1 Content model: base apps × fault library

You don't write hundreds of apps. You write **3–4 realistic base apps** and a **library of composable faults**, and every scenario combines the two.

| Base app | Stack | Teaches |
|---|---|---|
| **ShopKart** (e-commerce) | FastAPI api, worker (orders queue), Postgres, Valkey cache, Toxiproxy in front of the datastores | DB, caching, queues, deploys |
| **Shortly** (URL shortener, read-heavy) | Go or Python api, Postgres, Valkey | Hot keys, indexes, rate limits |
| **Chatter** (realtime chat) | WebSocket server, Valkey pub/sub, Postgres | Connections, backpressure, memory |
| **Ledger** (payments) | api, worker, Postgres (strict invariants) | Concurrency, idempotency, double-spend |

Each base app:
- exposes Prometheus metrics,
- logs structured JSON,
- ships with a seed dataset, a load profile (k6) and a `healthz`,
- has a **baseline SLO**.

Each base app is built once into pinned image digests.

### 11.2 Scenario package (scenario-as-code)

```
content/scenarios/caching/big-sale-meltdown/
├─ scenario.yaml        # metadata, story, faults, beats, probes, constraints, flags
├─ inject/              # code patches (unified diff), config overrides, data scripts
├─ verify/              # k6 scripts, invariant SQL, hidden tests (pytest), chaos steps
├─ hints.md             # tier 1 nudge · tier 2 direction · tier 3 near-answer
├─ solution/            # reference fix (patch) + explanation.md
├─ approaches/          # known approaches (yaml): idea, exemplar patch, outcome, pros/cons
└─ rubric.yaml          # postmortem grading criteria with anchors
```

```yaml
# scenario.yaml (abridged): validated by packages/py-content (Pydantic → JSON Schema)
schema: devgrill/scenario@1
slug: big-sale-meltdown
title: The Big Sale Meltdown
track: caching
topic: stampedes
difficulty: sev2
est_minutes: 25
base_app: shopkart@4
story:
  role: On-call engineer at ShopKart
  briefing_md: briefing.md
  page: { severity: SEV1, title: "product-api p99 > 3s, error rate 18%" }
faults:
  - use: cache/key-format-change     # fault module from content/faults
    at: "T-2m"                       # deployed 2 minutes before the sale
    params: { prefix: "v2:" }
  - use: load/sale-spike
    at: "T+0"
    params: { multiplier: 10, hot_keys: [1042, 1043, 2210] }
unlocked_tools: [overview, logs, terminal, database, cache, code, deploys, war_room]
flags: []
deploy_history: [ { sha: 7bd21e0, msg: "update product images" }, { sha: a91f3c2, msg: "refactor: add version prefix to cache keys", from_fault: cache/key-format-change } ]
beats:                               # deterministic teammate messages
  - at: "T+20s"   persona: priya   say: "Sale went live at 8 PM and product pages are dying…"
  - when: "postgres.restarted"   persona: arjun   say: "Restart didn't hold. Something is *sending* it too many queries. What changed?"
  - when: "state:mitigated"   persona: arjun   say: "Rollback holds. Make the read path stampede-proof, then verify."
mitigation:
  detect: { slo: "p99_latency_ms < 500 and error_rate < 0.01", for: "60s" }
constraints:
  - no_scale_up: [postgres]
  - redis_max_memory_mb: 1024
probes:
  - key: sale-replay      kind: load        script: verify/sale.k6.js   target: { p99_ms: { lt: 500 }, error_rate: { lt: 0.01 } }
  - key: hot-key-expiry   kind: chaos       steps: [ { del_key: "product:1042" } ]  target: { db_qps_product: { lt: 50 } }
  - key: cold-cache       kind: chaos       steps: [ { flushall: true } ]           target: { recovery_s: { lt: 30 } }
  - key: price-freshness  kind: invariant   script: verify/freshness.py           target: { visible_after_s: { lt: 5 } }
  - key: correctness      kind: hidden_test path: verify/tests/
  - key: budget           kind: budget      target: { constraints: all }
scoring:
  weights: { mitigation_time: 0.25, resolution: 0.4, postmortem: 0.25, communication: 0.1 }
```

**Fault modules** (`content/faults/<category>/<name>/fault.yaml` plus files) declare:
- their `kind` (code_patch, config, toxic, resource, data, infra),
- parameter schema,
- an apply step and a revert step,
- the **observable symptom contract**, for example "error_rate rises above 5% within 60s".

The validation pipeline asserts that symptom contract (see §11.3).

### 11.3 Validation pipeline (CI and the `devgrill-content validate` command)

1. **Schema:** `scenario.yaml` against the JSON Schema; referenced files exist; fault params are valid.
2. **Build:** base app and scenario overlay images build, and their digests are recorded.
3. **Breaks:** boot → apply faults → run load → assert that the **symptoms appear** (the SLO is violated and the alert fires).
4. **Fixable:** apply `solution/` → run **all probes** → all pass.
5. **Approaches:** each known approach in `approaches/` produces its declared outcome (full, partial or fails).
6. **Anti-cheat:** the cheat fixes must **fail** correctness or budget probes. The standard set is: return 503 everywhere, disable the endpoint, delete data, and scale up beyond constraints.
7. **Solver (phase 10, optional in CI):** an AI solver agent attempts the scenario within a step budget. Its success rate and step count seed the difficulty and the initial Glicko rating.
8. **Report:** `validation_report.json` is attached to the `scenario_version` and shown in the admin console.

### 11.4 Content lifecycle and CMS

```
draft (git branch) ──PR──▶ CI validation ──▶ review (admin console: playtest + checklist)
   ──▶ published (scenario_version immutable, attempts pin it)
   ──▶ analytics (solve rate, median time, hint use, drop-off, rating drift)
   ──▶ revise (new version) or retire
```

- **Source of truth:** the git `content/` folder. `devgrill-content publish` syncs it into the `scenarios`, `scenario_versions` and related tables, and pushes images.
- **Admin console** (`/admin`):
  - Review queue with a playtest button that launches a sandbox in "author mode" (solution visible, faults toggleable).
  - Validation reports.
  - Per-scenario analytics with automatic flags ("solve rate < 10%", "median time > 2× estimate", "high drop-off at Cache panel").
  - Approach clustering review.
  - Retire and replace.
- **Contribution paths:**
  1. **You:** about 30 high-quality scenarios at launch.
  2. **AI generator:** proposes variants and new faults, which go through the same validation and review (phase 10).
  3. **Invited authors** (optional, later): trusted engineers get access to the private content repo and the admin console, with credit on the scenario page. The platform and content stay closed source (owner decision).
  4. **Postmortem replays:** curated public postmortems (e.g. the `danluu/post-mortems` list), rebuilt as mechanisms on a base app. These drive the Weekly Outage.

### 11.5 Coverage map (the "sheet")

| Track | Topics (each with a primer and 3–6 scenarios, SEV4 to SEV1) |
|---|---|
| Databases | Indexes, connection pools, locks and deadlocks, migrations, replication lag, query plans |
| Caching | Stampedes, invalidation, hot keys, eviction and memory, key changes |
| Queues and async | Poison messages, consumer lag, idempotency, retries and DLQ, ordering |
| Concurrency | Race conditions, deadlocks, double spend, thread pools |
| Memory and CPU | Leaks, runaway regex, GC pauses, thread starvation, file descriptors |
| Networking | Timeouts, retry storms, DNS, TLS expiry, circuit breakers, connection reuse |
| Deploys and config | Bad config, feature flags, version skew, migrations-in-deploy, secrets rotation |
| Distributed systems (capstones) | Cascading failure, clock skew, split brain, thundering herd, partial outages |

**Systematic sources:**
- Stability antipatterns (*Release It!*)
- The Google SRE Workbook (Wheel of Misfortune)
- Chaos-tool fault taxonomies (Toxiproxy, Chaos Mesh)
- Issue trackers of Postgres, Redis and Valkey, and popular frameworks
- Public postmortems

---

## 12. Sandbox infrastructure

### 12.1 The `SandboxDriver` interface

As built in Phase 3 (`devgrill/sandbox/driver.py`, ADR 012). The handle is derived from the attempt id, so teardown never depends on provisioning having returned:

```python
class SandboxDriver(Protocol):
    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...  # idempotent: clean slate
    async def wait_healthy(self, handle, timeout_s: int) -> None: ...
    async def apply_fault(self, handle, bundle, use: str, params: dict) -> None: ...
    async def revert_fault(self, handle, bundle, use: str, params: dict) -> None: ...
    async def start_load(self, handle, bundle, *, multiplier: float = 1.0) -> None: ...
    async def stop_load(self, handle) -> None: ...
    async def exec(
        self, handle, service: str, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult: ...
    async def probe(
        self, handle, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult: ...  # verifier side
    async def deploy(
        self, handle, bundle, service: str, ref: str | None = None
    ) -> DeployResult: ...
    async def restart(self, handle, service: str) -> None: ...
    def logs(self, handle, *, since=None, tail=200) -> AsyncIterator[LogLine]: ...
    async def metrics(self, handle, bundle) -> MetricSnapshot: ...  # raw scrapes per job
    async def usage(self, handle) -> ResourceUsage: ...  # cpu_seconds for cost tracking
    async def destroy(self, handle) -> None: ...  # by label; safe to repeat
    async def list_sandboxes(self) -> list[str]: ...  # orphan sweeper, leak checks
```

`exec_pty`, `read_file` and `write_file` come with the gateway in Phase 4. Firecracker snapshots come later still.

Every scenario is runtime-agnostic. Scenario content may also declare a **process mode** (services under supervisord in one VM, with no nested Docker). That lets scenarios run on hosted providers that can't do Docker-in-Docker.

### 12.2 Progression

| Stage | Driver | Where | Isolation | Notes |
|---|---|---|---|---|
| Local dev (phase 3+) — **the only stage in scope until hosting is decided** | `ComposeDriver` | Docker Desktop on Windows | Per-session compose project + **`internal: true` network** (no egress) | Fast iteration. Isolation not required locally |
| Hosted beta (Track H, deferred) | `SysboxDriver` | 1× dedicated Linux host (~64 GB, Ubuntu 24.04, kernel ≥ 5.19) | One **Sysbox system container per session** running its own dockerd + pre-baked inner images; nftables default-deny egress; cgroup v2 limits (`cpu.max`, `memory.max` no swap, `pids.max`, `io.max`); fixed-size rootfs | ~25–40 concurrent sessions/host (estimate; measure in phase 8). Breakeven vs hosted ≈ 400 session-hours/month |
| Bridge option (Track H, deferred) | `ModalVMDriver` / Fly Machines | Hosted | VM | Pay-per-use alternative to owning a server. Modal documents Docker in its VM runtime; prototype before committing |
| Scale (phase 10+) | `FirecrackerDriver` | Bare-metal pool | microVM per session, custom guest kernel (netfilter, overlay, bridge), OCI → ZFS/dm-thin CoW rootfs, **per-scenario warm snapshots** (sub-second to ~3s start), vsock guest agent for PTY, logs and metrics, jailer | Months of work: evaluate forking E2B's open-source infra vs building |

### 12.3 Gateway, terminal and telemetry

- **Terminal path:**
  1. Browser xterm.js connects over WSS (ticket) to the gateway.
  2. The gateway runs `driver.exec_pty` (docker exec with a TTY into a `tools` container that has `psql`, `redis-cli`, `curl`, `git`, the `devgrill` CLI and `tmux`).
  3. Binary frames carry data; control messages carry `resize` and `ping`.
  4. `tmux` keeps the session alive across reloads.
  5. Sessions are recorded as asciicast to object storage (SeaweedFS locally). The recording powers the replay and gives the AI its context.
- **In-sandbox CLI** (`devgrill`, named `gym` in early mockups): `status`, `logs`, `restart <svc>`, `deploy`, `rollback`, `flags`. It is a thin client that calls the gateway's sandbox-control API, and every call is logged as an `attempt_event`.
- **Telemetry (MVP):**
  - The gateway scrapes exporters (app, postgres_exporter, redis_exporter, Toxiproxy) every 1–2s.
  - It tails docker logs.
  - It multiplexes both over the telemetry WebSocket. The UI charts with uPlot.
  - A rolling 30-minute window is kept in Valkey for `/telemetry` history.
- **Telemetry (scale):** Vector agent → VictoriaMetrics + VictoriaLogs (session ID as structured metadata, not a label). **Never expose raw Grafana to users.**
- **The verifier runs outside the sandbox:** a k6 container attaches to the session network from the host side. Chaos steps run through Toxiproxy's API, and data invariants run as SQL through a read-only role. Root inside the sandbox cannot tamper with them.

### 12.4 Capacity, cost, quotas and access tiers (ADR 013)

**Three content formats.** Only one of them needs a sandbox:

| Format | Sandbox | Free plan |
|---|---|---|
| Quick Fire cards | no | unlimited |
| **Case files**: recorded evidence from a real run of a live scenario (logs, metrics, deploys, code). The player names the root cause, the mitigation and the fix. Generated by `devgrill-content record` | no | unlimited |
| Live incidents | yes | `access: free` scenarios plus the Daily Incident, within a weekly allowance |

**Plan limits.** These are initial values. They live in `entitlements.limits`, with defaults in `devgrill.domain.entitlements`. Days and weeks roll over at 00:00 IST.

| Limit | Guest (`/try`) | Free | Pro |
|---|---|---|---|
| Live scenarios | tutorial only | `access: free` + Daily | all |
| Concurrent sandboxes | 1 | 1 | 1 |
| Live starts | 1 per token, per-IP cap | 3 per week | fair use: 10 per day |
| Sandbox minutes | 20 | 120 per week | 240 per day |
| Session TTL / idle | 20 / 5 min | 30 / 8 min | 60 / 10 min |
| `extend` | no | no | +15 min ×2 |
| AI teammate messages | 10 | 20 per day | 200 per day |
| AI postmortem reviews | 0 | 2 per week | 20 per day |

**Bill guarantee: four independent layers.** Each layer caps cost even if the one before it fails.
1. **Per sandbox:** cgroup CPU, memory and pids limits; no egress; TTL and idle teardown in the workflow's `finally`.
2. **Per user:** the plan limits above, enforced at `POST /v1/attempts`:
   - `403 upgrade_required` when the scenario isn't in the plan;
   - `429 quota_exceeded` with `Retry-After` set to the next rollover.
3. **Fleet:** `SANDBOX_MAX_LIVE` caps concurrent sandboxes. Past it, starts queue ("You're #3, about 40s") or get `503 capacity` with `Retry-After`.
4. **Money:** `SANDBOX_DAILY_MINUTES_BUDGET` caps the total free and guest minutes per IST day.
   - An alert fires at 80%.
   - At 100%, free starts pause until midnight (`503 budget_paused`) with an honest message, and cards and case files stay open. Pro is unaffected.
   - `SANDBOX_FREE_STARTS=false` is the kill switch.
   - A matching LLM budget comes in Phase 6.

**Metering:**
- Minutes run from `active` to teardown. Provisioning time is tracked but not charged to the player.
- The idle timer resets on player input: terminal keystrokes, actions and panel use. Sandbox CPU activity does not reset it.
- Per session, `cpu_seconds` and `est_cost_usd` are recorded.

**Cost tracking:**
- Dashboards: cost per resolved incident, cost per active user.
- Alerts at budget thresholds.

**Unit cost** (research, 2026-10-20):
- A Hetzner AX41 (64 GB, about €50/month) fits about 25–35 sandboxes by memory. That's about €0.01 per sandbox-hour at 30% utilisation, or under ₹1 per session.
- **Measured in Phase 3** (`docs/perf/phase-3.md`): one ShopKart sandbox under sale load uses about 580 MiB but about 2.6 CPU cores, the load generator included. **CPU, not RAM, bounds density.**
  - Before Track H, lower the play-time load to what still shows the incident.
  - Measure density on the real host (Phase 8).
- Cloud VMs are 5–15× more per sandbox-hour.
- LLM calls, not sandboxes, are the larger variable cost.

**Pre-warmed pool:** keep N booted sandboxes of the Daily Incident ready (driver-dependent).

---

## 13. AI system

All AI features use the **OpenAI Responses API** behind an internal `LLMClient` port (`devgrill.infra.llm`). That port provides:
- model routing,
- structured outputs (`responses.parse` → Pydantic),
- timeouts and retries with jitter,
- a fallback model,
- a **per-feature, per-user and per-day budget**,
- `llm_calls` cost metering,
- Langfuse tracing,
- a prompt registry (versioned prompts in `packages/py-core/devgrill/ai/prompts/*.md`, mirrored to Langfuse).

### 13.1 Model routing (re-check prices at implementation time)

| Feature | Model | Why |
|---|---|---|
| War-room persona replies, mentor nudges, Quick Fire explanations | `gpt-6-luna` ($0.10 / $0.50 per 1M tokens) | High volume, low latency, cheap |
| Postmortem grading, approach classification, debrief coaching notes | `gpt-6.1-sol` ($2 / $10) with structured outputs | Judgment quality |
| Scenario generator and solver agent (OpenAI Agents SDK) | `gpt-6.1-sol` by default, escalating to `gpt-6-astra` ($10 / $50) on hard cases | Agentic coding |
| Embeddings (approaches, scenario search, dedupe) | `text-embedding-3-small` (1536 dimensions) | Fits pgvector HNSW |

### 13.2 Features

1. **War-room teammates.**
   - Scripted beats come from `scenario.yaml` and are deterministic.
   - Free-form replies come from persona prompts (PM, SRE, IC) built from:
     - the scenario story,
     - the current state,
     - the **redacted** trail summary,
     - the hint ladder **up to the user's unlocked tier**.
   - Personas never reveal the root cause or the solution. They ask Socratic questions.
2. **Mentor hints.**
   - Tiers 1–3 are authored, so they are free and deterministic.
   - In Guided mode, an optional LLM nudge is anchored to the authored tier and the user's last 20 trail events.
   - Hints reduce the score and the rating gain.
3. **Postmortem grading.**
   - The rubric criteria have anchored score levels.
   - The judge gets: the rubric, the facts (true root cause, the timeline from the trail, probe results) and the postmortem.
   - It returns per-criterion scores, quotes from the postmortem as evidence, and feedback.
   - Blamelessness check: describe the change, not the person.
   - **Calibration:**
     - 60 hand-graded postmortems form a golden set.
     - The judge must be within ±1 point on ≥ 85% of criteria and reach Spearman ≥ 0.8 on totals before launch.
     - It is re-run on every prompt or model change.
4. **Approach classification.**
   - Inputs: the diff + probe metrics fingerprint (DB QPS at expiry, staleness, p99), plus embedding similarity to known approaches.
   - The LLM picks a known approach or `unknown` with a rationale.
   - Unknown approaches are clustered (pgvector) and sent to the admin review queue, where they can be promoted to known approaches.
5. **Debrief coach note.**
   - One paragraph built from the trail: where time was lost and the key clue that was missed.
   - Uses structured outputs that cite trail events by ID, so nothing is invented.
6. **Scenario generator and solver (phase 10).**
   - Agents SDK workflows inside Temporal.
   - The generator proposes a fault plus a story plus probes on an existing base app.
   - The validation pipeline (§11.3) proves the scenario breaks and can be fixed.
   - The solver agent attempts it with tools (`exec`, `read_logs`, `query_metrics`, `edit_file`, `deploy`, `verify`) under a step and cost budget, **in its own sandbox**.
   - A human always reviews before publishing.

### 13.3 AI safety and integrity

- **Prompt injection:** terminal output, logs, code and user text are **untrusted**. They are wrapped in delimited data blocks with an explicit "data, not instructions" policy. Tools are never exposed to user-facing personas, so personas can only talk.
- **No AI actions in user sandboxes.** The solver agent only ever runs in its own sandboxes.
- **Privacy:**
  - Strip emails and tokens from trail context.
  - Langfuse retention: 30 days.
  - Postmortems are used for grading. Training use requires opt-in and must be disclosed.
- **Evaluation suite** (`evals/`):
  - Golden sets for grading, classification and persona behaviour (for example, "never reveals the root cause in 50 adversarial prompts").
  - Runs in CI on prompt or model changes. Blocks merge if metrics regress beyond tolerance.
- **Budgets:**
  - Per-user daily caps by plan.
  - A global daily spend alarm.
  - Graceful degradation: authored hints only, with a "teammates are busy" state.

---

## 14. Quality framework

Every phase gate (§15) contains these **standard checks** plus the phase-specific ones.

### 14.1 Definition of Done (per task or PR)

- [ ] Code is typed (basedpyright strict on `py-core`; TS `strict`), linted (ruff, ESLint) and formatted.
- [ ] Tests are added or updated at the right level (see the pyramid below), and CI is green.
- [ ] OpenAPI is updated, the client is regenerated with no drift, and Schemathesis passes.
- [ ] UI work has stories for every state (empty, loading, error, success; light and dark; reduced motion) and axe reports no violations.
- [ ] Migrations follow the safe-migration checklist and are reversible in dev.
- [ ] Observability: logs are structured with `attempt_id` and `user_id`; spans exist on external calls; errors reach Sentry.
- [ ] Docs: an ADR for any architectural decision; README or runbook updated.

### 14.2 Test pyramid and targets

| Layer | Tooling | Target |
|---|---|---|
| Domain unit (pure) | pytest | ≥ 90% line coverage on `devgrill.domain`; property tests (hypothesis) for scoring and Glicko |
| Service / integration | pytest + testcontainers (Postgres, Valkey), fake drivers and LLM | All repositories and routers; ≥ 80% on `apps/api` |
| Contract | Schemathesis against the live app in CI | 0 failures; every endpoint covered |
| Workflow | Temporal test env (time-skipping) | Lifecycle, TTL, teardown-on-failure, verify ordering |
| Scenario | `devgrill-content validate` (break → fix → approaches → anti-cheat) | Every published scenario, on every content PR and nightly |
| Frontend unit | Vitest + Testing Library | Hooks, reducers, formatters; critical components |
| Visual / interaction | Storybook + test-runner (+ optional Chromatic) | All `packages/ui` components |
| E2E | Playwright (+ @axe-core/playwright) | Core loop: guest tutorial, sign-in, start → mitigate → verify → postmortem → debrief; Quick Fire on mobile viewport |
| AI evals | `evals/` golden sets | Grading agreement ≥ 85% within ±1; persona leak rate 0/50; classification accuracy ≥ 85% on labelled set |
| Load | k6 against staging | Phase 8: 50 concurrent sessions, API p95 < 150ms reads / < 400ms writes |

### 14.3 CI pipeline (GitHub Actions)

`lint+types` → `unit` → `integration` (services) → `contract` → `build images` → `e2e` (compose stack) → `a11y + Lighthouse CI` → `security` (gitleaks, pip-audit, pnpm audit, Trivy) → `content validate` (changed scenarios) → `evals` (when prompts or models change).

**Required on `main`:** branch protection, conventional commits, and squash merges.

### 14.4 Budgets

| Area | Budget |
|---|---|
| Web vitals (p75) | LCP < 2.0s (marketing), < 2.5s (app); INP < 200ms; CLS < 0.05 |
| JS per route (gzip) | Marketing ≤ 150KB · App pages ≤ 250KB · Workspace ≤ 450KB (xterm, CodeMirror and uPlot lazy-loaded per panel) · Mobile routes ≤ 180KB |
| API | p95 < 150ms reads, < 400ms writes (excluding 202-async) |
| Terminal | Keystroke echo < 80ms local, < 150ms remote (p95) |
| Sandbox | Time to active: < 45s with ComposeDriver (dev), < 20s with Sysbox and pre-baked images, < 5s with Firecracker snapshots |
| Telemetry | Metric sample to chart < 2.5s |
| AI | Persona first token < 1.5s p95; grading < 20s |
| Cost | Track sandbox $/resolved incident and LLM $/active user from phase 5 |

### 14.5 Design and UX QC procedure (end of every phase that touches the UI)

1. Run the vendored skills against the changed UI:
   - `web-design-guidelines` (layout, typography, forms, interactions)
   - `accessibility` (WCAG 2.2)
   - `review-animations` (motion)
   - `vercel-react-best-practices` (perf)
2. Capture light and dark screenshots of every changed template at 1440, 1024 and 390 widths. Save to `docs/design/qc/phase-N/`.
3. Check against the token rules: no raw hex in components, only semantic tokens; tabular numbers; severity encoded three ways; serif never inside the workspace.
4. Keyboard-only run-through of the changed flows. From phase 4, add an NVDA pass on the core loop.
5. Reduced-motion run-through.
6. From phase 4, run 3–5 moderated user sessions per UI phase (friends or colleagues are fine). Log issues; P0/P1 must be fixed before the gate.
7. Write `docs/design/qc/phase-N.md`: findings, fixes and accepted deviations.

### 14.6 Bug severity policy (yes, we use SEV levels too)

- **SEV1:** data loss, security, or the core loop broken. Fix immediately; it blocks any gate.
- **SEV2:** major feature broken or an a11y blocker. Blocks the gate.
- **SEV3:** degraded but with a workaround. Fix or schedule with a date.
- **SEV4:** polish. Goes to the backlog.

---

## 15. Phased roadmap

**Timeline at 15–20 hrs/week:**

| Milestone | Week | What it means |
|---|---|---|
| **M0** | ~2 | Scaffold green |
| **M1** | ~20 | Vertical slice: one scenario playable end to end locally, with verify and debrief |
| **M2** | ~32 | Local release candidate: ~20 scenarios, hardened, playtested by 10+ engineers on this machine |
| **M3** | ~36 | Launch-ready: growth features done; public launch waits on Track H (hosting + pricing), which can start whenever the owner decides |

After M3, growth and scale continue (phase 10, ongoing). Treat week numbers as estimates and re-plan at every gate.

```
Wk:  1  2 | 3  4  5 | 6  7  8 | 9 10 11 12 | 13 14 15 16 17 | 18 19 20 | 21 22 23 | 24 25 26 27 28 | 29 30 31 32 | 33 34 35 36 | 37+
     P0   |   P1    |   P2    |     P3     |       P4       |    P5    |    P6    |       P7       |     P8      |     P9      | P10
     M0                                                            M1                                           M2            M3
```

---

### Phase 0: Foundations and scaffold (weeks 1–2) ✅ done 2026-10-13 (see docs/qc/phase-0.md)

**Goal:** a monorepo where every app boots locally with one command, CI is green, and decisions are recorded.

**Tasks**

1. **Machine setup:**
   - Native Windows (owner decision). Install `uv`, `pnpm@12`, `just` and GitHub CLI (`winget`).
   - Configure the corporate CA (`NODE_OPTIONS=--use-system-ca`, `UV_SYSTEM_CERTS=1`).
   - Docker Desktop resources: ≥ 8 GB RAM, 4 CPUs.
   - `git config core.autocrlf false`.
2. **Repo:**
   - `git init` with the layout from §6.
   - `.editorconfig`, `.gitattributes` (`* text=auto eol=lf`), `.gitignore`.
   - **Proprietary licence** (owner decision: closed source). Add a `LICENSE` stating all rights reserved; a **private** GitHub repo.
   - `CLAUDE.md` (Appendix E).
   - This plan moved to `docs/PLAN.md`.
3. **Python:**
   - uv workspace root `pyproject.toml` (`requires-python = ">=3.14,<3.15"`).
   - Members: `apps/api`, `apps/gateway`, `apps/worker`, `packages/py-core`, `packages/py-content`.
   - Shared ruff and basedpyright config.
4. **JS:**
   - `pnpm-workspace.yaml`, `turbo.json`.
   - `apps/web`: `create-next-app` with Next 16, TS ~6, Tailwind v4, App Router, `src/` off.
   - `packages/ui` (shadcn init on Base UI), `packages/tokens`, `packages/config`, `packages/api-client`.
5. **Platform services:** `infra/compose/docker-compose.dev.yml` with:
   - `pgvector/pgvector:0.8.7-pg18-trixie`
   - `valkey/valkey:9.1`
   - `seaweedfs` (S3 API; MinIO stopped publishing community images)
   - Temporal dev server (CLI container; no Windows binary needed)
   - `mailpit` (local email, for testing notifications)

   Add named volumes, healthchecks, and `.env.example`.
6. **FastAPI skeleton:**
   - App factory, settings, structlog JSON, OTel and Sentry hooks (disabled by default).
   - `/healthz` and `/readyz`.
   - Problem+json error handler.
   - Async SQLAlchemy engine and Alembic async env with the first migration (create schema `app`).
7. **Worker skeleton:** a Temporal worker running a `Ping` workflow. **Gateway skeleton:** a FastAPI WS echo.
8. **Codegen:** `pnpm gen:api` exports FastAPI OpenAPI and runs `@hey-api/openapi-ts` into `packages/api-client`.
9. **Task runner:** `just dev` starts compose deps plus api, worker, gateway and web (honcho, or turbo + uv run). Also `just test`, `just lint`, `just gen`, `just db-migrate`, `just db-reset`.
10. **CI:** GitHub Actions for lint, types, unit, build, and a compose smoke test hitting `/readyz` and the web root. Add Dependabot or Renovate.
11. **ADRs 001–008:**
    1. Monorepo layout
    2. FastAPI + uv
    3. Temporal for workflows
    4. Valkey
    5. Better Auth + JWT to FastAPI
    6. Hey API client
    7. SandboxDriver abstraction
    8. ESLint+Prettier vs Biome

**Deliverables:** a running skeleton, CI, ADRs, `README` with setup steps (including the proxy notes).

**QC gate: Phase 0**

- [ ] Fresh clone to `just dev` works in **≤ 15 minutes** on this Windows machine in **PowerShell** (tested by recloning into a new folder), and CI proves the same steps on Linux.
- [ ] Line-ending check: no CRLF in `*.sh`, `Dockerfile*`, `*.yaml` (CI check).
- [ ] `/readyz` reports DB, Valkey and Temporal OK; the Temporal `Ping` workflow completes; the web root renders.
- [ ] CI is green on an empty PR; branch protection is on.
- [ ] `pnpm gen:api` is deterministic (no diff on a second run).
- [ ] gitleaks is clean; `.env` is git-ignored; `.env.example` is complete.
- [ ] ADRs 001–008 are merged.
- [ ] Vendored skills are present in `.claude/skills` with `VENDORED.md`; `CLAUDE.md` references them.

---

### Phase 1: Design system and app shell (weeks 3–5) ✅ done 2026-10-13 (see docs/qc/phase-1.md; owner sign-off on the "Not LeetCode" review pending)

**Goal:** the product looks and feels like DevGrill before any feature exists. Tokens, typography, components and page templates are built as static shells with mock data.

**Tasks**

1. **`packages/tokens`:**
   - `tokens.json` (primitives + semantics from §7.2, motion, radius, spacing, z-index).
   - Generator script (OKLCH palette + contrast check) outputs `tokens.css` (light, `.dark`, P3 media) and `tokens.ts`.
   - **The contrast test runs in CI and fails if any declared pair drops below its target.**
2. **Tailwind v4 preset:** `@theme inline` mapping; CVA variant conventions (`tailwind-design-system` skill).
3. **Fonts:** `next/font/google` (Instrument Sans, Instrument Serif, JetBrains Mono, Bricolage Grotesque) with subsets, `display: swap`, CSS variables, and size-adjusted fallbacks to avoid CLS.
4. **Theming:** own `ThemeProvider` (ADR 010; system default), theme toggle, no-flash script, reduce-motion preference (OS + in-app) exposed as a `data-motion` attribute.
5. **Components:**
   - shadcn/Base UI base set restyled to tokens.
   - Custom set from §7.7 as **visual shells**, fed mock data: SevBadge, StatusPill, ProbeRow, ApproachCard, RatingDelta, MasteryRing, StreakFlame, EmptyState, BootSequence, IncidentTimeline, ToolRail.
   - `MetricChart` (uPlot) with a mock stream.
   - `CommandPalette` (cmdk).
   - `WorkspaceLayout` (react-resizable-panels + presets + focus mode).
6. **Storybook 10:** all components; a11y addon; theme and motion toolbar; interaction tests for palette, panels and tabs.
7. **Templates T1–T11 (§8.2):** static pages wired with mock JSON, including the **workspace shell** with fake terminal output and a fake log stream, to validate density and layout.
8. **Motion primitives:** `motion` presets matching the §7.5 tokens; View Transitions for route changes; a celebrate sequence prototype for the debrief.
9. **Iconography:** lucide setup; SEV glyph set; 6 service icons.
10. **Brand basics:** wordmark (Instrument Sans with a custom "S" pager notch, or plain), favicon, OG image template (Arcade layer).

**Deliverables:** Storybook, a static clickable prototype of all templates in both themes, and `docs/design/system.md`.

**QC gate: Phase 1**

- [ ] **Contrast CI test passes** for every semantic pair in both themes (≥ 4.5:1 text, ≥ 3:1 UI marks).
- [ ] No raw colour values in `apps/web` or `packages/ui` (lint rule or grep check); only semantic tokens.
- [ ] Every component story covers light, dark, reduced motion and all states; axe reports 0 violations in Storybook.
- [ ] Keyboard: ⌘K palette, panel resize via keyboard (splitter pattern), focus mode, tab order are all correct.
- [ ] Lighthouse on the T1 landing shell: Performance ≥ 95, Accessibility = 100, CLS < 0.05 (fonts don't shift).
- [ ] The design QC procedure (§14.5) is run with `frontend-design`, `web-design-guidelines`, `accessibility` and `review-animations`, and the report is in `docs/design/qc/phase-1.md`.
- [ ] **"Not LeetCode" review:** a side-by-side screenshot comparison with LeetCode, HackerRank and a generic indigo SaaS. Owner sign-off that DevGrill reads as its own brand.
- [ ] Workspace shell is usable at 1024px and redirects to the mobile experience under 768px.

---

### Phase 2: Domain, database, auth and API skeleton (weeks 6–8) ✅ done 2026-10-13 (see docs/qc/phase-2.md and ADR 011)

**Goal:** real users can sign in, and the catalog and progress APIs serve real data from Postgres to the UI.

**Tasks**

1. **Better Auth in `apps/web`:**
   - **GitHub OAuth only** (owner decision). Use a GitHub OAuth App with callback `http://localhost:3000/api/auth/callback/github`. Keep the provider list in config so Google or email can be added later without code changes.
   - Postgres adapter writing to the `auth` schema.
   - JWT plugin with JWKS.
   - Session hooks that call `POST /internal/profiles` (HMAC-signed).
2. **FastAPI auth dependency:** verify JWT (EdDSA) with cached JWKS (rotating); `CurrentUser`; role checks; guest tokens (signed, httpOnly cookie) for `/try`.
3. **Alembic migrations** for the catalog, play, progression and platform tables (§9.2): enums, indexes, partial unique index for live attempts, the pgvector extension.
4. **Domain layer (`devgrill.domain`):**
   - Entities and value objects (Attempt state machine with allowed transitions, Scenario, Probe, Score, Rating).
   - **Glicko-2 implementation** with property tests.
   - Streak computation.
5. **Repositories and services:** async SQLAlchemy repositories; unit-of-work per request; idempotency middleware (Valkey); rate-limit dependency.
6. **Routers:** catalog (`/tracks`, `/scenarios`), `/me`, `/me/ratings`, `/me/progress`, `/me/streak`, `/me/attempts` (read-only for now), admin read endpoints.
7. **Seed data:** `just db-seed` loads tracks, topics and placeholder scenarios from `content/` metadata.
8. **Web integration:**
   - Generated client + TanStack Query.
   - Server Components fetch catalog data with a JWT forwarded from the session.
   - Library, Track and Briefing templates now render real data.
   - Profile and settings persist prefs (theme, reduce motion, pro mode).
9. **Errors and observability:** problem+json mapped to UI error states; request IDs end to end; Sentry on both sides (dev DSN optional).

**Deliverables:** sign-in, a real catalog, profile, settings, and migrations.

**QC gate: Phase 2**

- [ ] Auth e2e (Playwright): GitHub flow (mocked IdP in CI, real GitHub OAuth App locally), sign-out, session expiry, guest token issuance, guest → account claim.
- [ ] Expired, tampered and wrong-audience JWTs return 401; JWKS rotation is tested.
- [ ] Schemathesis passes for all `/v1` endpoints; contract drift check passes.
- [ ] Migrations: upgrade then downgrade then upgrade works on an empty DB; the safe-migration checklist is followed; `EXPLAIN` checked for library queries (index use, < 20ms on 10k scenarios of seed data).
- [ ] Glicko-2 matches the reference implementation's worked examples (Glickman's paper) to 1e-4.
- [ ] OWASP checks: authz tests for every admin route (403 for non-admin); rate limits enforced; CORS restricted to the web origin.
- [ ] Standard UI QC (§14.5) for the Library, Track, Briefing, Profile and Settings templates now that they show real data, including loading and error states.

---

### Phase 3: Scenario engine v1 (weeks 9–12) ✅ done 2026-10-20 (see docs/qc/phase-3.md, ADR 012 and ADR 013)

**Goal:** a real broken system boots locally on demand from content, with a guaranteed lifecycle. Still no UI beyond a debug page.

**Tasks**

1. **Base app ShopKart v1** (`content/base-apps/shopkart`):
   - FastAPI api, worker, Postgres with seed (about 18k products), Valkey cache.
   - Toxiproxy in front of Postgres and Valkey.
   - Prometheus metrics; postgres_exporter, redis_exporter.
   - JSON logs.
   - A `tools` container (psql, redis-cli, curl, git, tmux, `devgrill` CLI).
   - k6 load profiles (normal, sale).
   - A git repo of its source inside the sandbox, so `git log` shows a real history.
2. **Scenario spec:** Pydantic models for `scenario.yaml`, `fault.yaml` and `approach.yaml`, plus exported JSON Schema (for editor autocompletion).
3. **Fault modules (first 8):**
   - `cache/key-format-change`
   - `cache/ttl-zero`
   - `db/missing-index`
   - `db/pool-exhaustion`
   - `db/lock-migration`
   - `queue/poison-message`
   - `mem/leak-accelerated`
   - `config/bad-env`
4. **`ComposeDriver`** (Docker Engine API through aiodocker; no compose CLI):
   - A per-attempt project name. Every container and network is labelled, so a sweeper can find orphans.
   - One isolated `internal: true` network (no egress).
   - Nothing listens on the host. The platform reaches the sandbox only through the Docker API: exec, archive, logs, stats.
   - A platform-owned **probe** container on the sandbox network (curl, psql, k6). The player never gets a shell in it. It runs scrapes, the load, Toxiproxy admin calls and verifier checks, so root in the player's shell can't tamper with them.
   - Resource limits (`cpus`, memory, `pids_limit`). Image volumes become tmpfs, so a sandbox never leaves a volume behind.
   - Patchable services are a git repo in the shell (`/workspace/<service>`).
     - Deploy copies the working tree into the service and restarts it.
     - Config faults edit a committed `config/app.env` (config-as-code), so a bad config shows in `git log` and can be reverted.
   - Fault application (patch, env, toxic, script), logs, metric scrape, destroy.
5. **Temporal `SandboxLifecycle` workflow:**
   - provision → healthy → inject faults (timed: T-2m deploys) → start load → active.
   - Signals: extend, reset, abandon, verify.
   - TTL and idle timers; **teardown in `finally`, guaranteed**.
   - Writes state to the DB through activities; events go to Valkey pub/sub and the SSE endpoint.
6. **Content CLI** (`devgrill-content`): `validate`, `build`, `up <scenario>` (local play without the web app), `test` (break → fix check), `publish` (sync to DB).
7. **Scenarios 1–3** (fully authored, validated):
   - `big-sale-meltdown` (caching, SEV2)
   - `ttl-zero` (caching, SEV4, the tutorial candidate)
   - `pool-party` (DB pool exhaustion, SEV3)
8. **Attempt endpoints:** `POST /v1/attempts`, `GET`, `DELETE`, `/events` (SSE), `/extend`, `/reset`.
9. **Cost and metrics:** `sandbox_sessions` timing and `cpu_seconds` capture.
10. **Access and the bill guarantee (ADR 013):**
    - An `access: free | pro` field in the scenario spec, also stored on `scenarios`.
    - A pure policy, `devgrill.domain.entitlements`: plan limits and an allow-or-deny decision with a reason and `Retry-After`.
    - Usage counted from `sandbox_sessions` (minutes and starts per IST day and week).
    - Enforcement in `POST /v1/attempts`:
      - plan access → `403 upgrade_required`;
      - quotas → `429 quota_exceeded`;
      - fleet cap `SANDBOX_MAX_LIVE` → `503 capacity`;
      - free-minutes budget `SANDBOX_DAILY_MINUTES_BUDGET` and the `SANDBOX_FREE_STARTS` kill switch → `503 budget_paused`.
    - The workflow's TTL and idle timers come from the plan.
    - `GET /v1/me/usage` shows what is left.

**Deliverables:** `devgrill-content up big-sale-meltdown` reproduces the incident locally; API-driven attempts boot and tear down reliably; nobody can start more sandbox time than their plan and the global budget allow.

**QC gate: Phase 3**

- [ ] `devgrill-content test` passes for all 3 scenarios: **symptoms appear** (SLO violated within 60s) and **reference fix passes all probes**.
- [ ] Lifecycle reliability:
  - 50 sequential create→destroy cycles with 0 leaked containers, networks or volumes (checked by a script).
  - Killing the worker mid-provision still ends in a clean teardown after restart.
- [ ] Temporal workflow tests (time-skipping): TTL expiry, idle timeout, abandon, reset, worker crash.
- [ ] Sandbox network has **no egress** (a `curl https://example.com` from inside fails); the platform network is unreachable from the sandbox.
- [ ] Time to active < 45s on the dev machine with images pre-pulled; recorded in `docs/perf/phase-3.md`.
- [ ] Resource limits enforced (a fork bomb inside a sandbox is contained by `pids_limit`; memory hog OOMs only its own container).
- [ ] Entitlement policy unit-tested (every limit, IST rollover, Daily exception, guests). The API is tested for each refusal: 403, 429 and 503 return problem+json with `Retry-After`, and no sandbox is started.
- [ ] ADR for the fault-module contract and the scenario spec v1 (ADR 012); ADR 013 for access tiers.

---

### Phase 4: Incident workspace (weeks 13–17)

**Goal:** a person can play `big-sale-meltdown` in the browser with real tools: terminal, logs, metrics, database and cache views, code, deploys and a scripted war room.

**Tasks**

1. **Gateway service:**
   - Ticket auth.
   - WS terminal bridging to `exec_pty` in the tools container (binary frames, resize, keepalive, tmux attach), with asciicast recording to object storage.
   - Telemetry WS: scrape every 1–2s, log tail, multiplexed frames, backpressure (drop oldest log lines rather than blocking).
2. **In-sandbox control API + CLI** (`devgrill status | logs | restart | deploy | rollback | flags`). Every action emits an `attempt_event`.
3. **Workspace panels (real data):**
   - Overview (uPlot charts with SLO lines and deploy/sale markers)
   - Logs (virtualised, filter, pause, freeze)
   - Terminal (xterm, reconnect, screen-reader mode)
   - Database (top queries from `pg_stat_statements`, connections, read-only console)
   - Cache (stats, key browser, top missed keys)
   - Code (CodeMirror, file tree, save → write_file, Deploy ⌘⏎)
   - Deploys (history, rollback)
4. **Phase stepper and state:**
   - Mitigation detection: the workflow evaluates `mitigation.detect` against telemetry and moves the state to `mitigated` automatically.
   - Manual "declare mitigated" is scored against the real state.
5. **War room v1 (scripted):** beats from `scenario.yaml` (time-based and event-based), Incident Timeline, user status updates stored as events. LLM replies come in phase 6.
6. **Hints v1:** authored tiers 1–3, with hint use recorded.
7. **Command palette** wired to real actions; layout presets; focus mode; keyboard map (§8.4).
8. **`BootSequence`** driven by real workflow events; the expiry warnings and Extend flow.
9. **Resilience:** network loss banner, WS reconnect, sandbox-died state with "Reset" and "Report".

**Deliverables:** M1 minus verify, so the incident is playable through mitigation and fix.

**QC gate: Phase 4**

- [ ] E2E (Playwright, real ComposeDriver in CI or nightly): start → run commands in the terminal → see logs and metrics → roll back → state `mitigated` → edit code → deploy → service restarts.
- [ ] Terminal: keystroke echo p95 < 80ms locally; survives page reload (tmux); 30-minute session soak with no memory growth in the browser tab (> 20% heap growth fails).
- [ ] Telemetry: sample-to-chart < 2.5s; 1-hour stream with no unbounded memory (uPlot ring buffer verified).
- [ ] Workspace route JS ≤ 450KB gz initial; terminal, editor and charts lazy-loaded.
- [ ] Accessibility: full keyboard path through the core loop; splitters per WAI-ARIA; NVDA pass on Terminal (screen-reader mode), Logs, Timeline and War room; alerts announced via live regions as specified.
- [ ] Motion QC with `review-animations`: no animation on keyboard actions, no shimmer on streaming panels, reduced-motion respected.
- [ ] **Security:**
  - Gateway rejects reused or expired tickets and cross-user attempt IDs.
  - File API path traversal is blocked (`../`).
  - Terminal can't reach platform services.
- [ ] Usability: **3 moderated sessions** with engineers new to the scenario. At least 2 of 3 mitigate within 20 minutes; top 5 issues fixed or ticketed (SEV ≤ 3 only).
- [ ] Design QC report `docs/design/qc/phase-4.md`.

---

### Phase 5: Verify engine, scoring, debrief and ratings (weeks 18–20) → **M1 vertical slice**

**Goal:** close the loop. Verify attacks the fix, the score and rating update, and the debrief explains what happened.

**Tasks**

1. **`VerifyRun` workflow:**
   - A verifier container joins the session network from outside the sandbox.
   - Runs probes in order: load (k6 thresholds), chaos (Toxiproxy toxics, key deletion, restarts via the control API), invariants (SQL via a read-only role, HTTP checks), hidden tests, budget/constraint checks.
   - Stores results and artifacts; streams progress over SSE.
2. **Anti-cheat probes** are standard in every scenario: correctness tests catch "return 503 everywhere" and similar fake fixes.
3. **Scoring:**
   - Combines the `scoring.weights` from the scenario: mitigation time vs a par time, resolution (probe pass ratio, with partial credit), hints penalty, communication (status updates posted: counted now, graded by AI in phase 6).
   - The postmortem component is a placeholder until phase 6.
4. **Ratings:**
   - Glicko-2 update per track (the attempt as a match vs the scenario's rating; outcome from 0 to 1 derived from the score).
   - Guided mode and hints scale the gain down.
   - Scenario ratings update too. Rating history is stored.
5. **Postmortem editor v1:** a template with the timeline auto-inserted from the trail; save and submit (ungraded for now).
6. **Debrief page:**
   - Result hero with the celebrate sequence.
   - Probe table.
   - Your fix vs known approaches (manual mapping from `approaches/` until phase 6).
   - Investigation replay (trail with "lost time" and "key clue" markers from authored rules).
   - Rating delta; next drills.
7. **Approach reveal gating:** `/approaches` only after the scenario is resolved.

**Deliverables (M1):** one scenario fully playable end to end locally, plus scenarios 2 and 3 playable.

**QC gate: Phase 5 (M1)**

- [ ] For each scenario: reference fix → verify **passes**. Each known approach gives its declared outcome. Each cheat fix **fails** (automated in content tests).
- [ ] Verify is tamper-proof: deleting or modifying anything inside the sandbox (as root) cannot make a broken fix pass (red-team checklist of 10 attempts, documented).
- [ ] Verify duration < 4 minutes per scenario; progress is visible the whole time; re-running verify is idempotent.
- [ ] Scoring and Glicko property tests: monotonic in mitigation time; hints never increase the score; rating deltas are bounded and correct sign.
- [ ] E2E: the full loop through to the debrief in CI nightly.
- [ ] Debrief celebration is skippable and fully disabled under reduced motion; accessible headings and table semantics.
- [ ] **M1 demo:** a recorded 5-minute screen capture of the full loop, plus a retrospective doc (what to cut or keep, re-estimate remaining phases).

---

### Phase 6: AI layer (weeks 21–23)

**Goal:** teammates talk, postmortems get graded, fixes get classified, and every AI cost is metered.

**Tasks**

1. **`LLMClient` port:** OpenAI Responses API adapter, structured outputs, retries, timeouts, fallback model, per-feature budgets, `llm_calls` metering, prompt registry with versions.
2. **Langfuse** self-hosted via `infra/compose/docker-compose.langfuse.yml` (it needs ClickHouse, Valkey and S3; the local SeaweedFS S3 API is reused); OTel traces linked to `attempt_id`.
3. **Persona replies** (`gpt-6-luna`) streamed over SSE, with untrusted-data fencing, a hint-tier ceiling, and no-solution-leak guardrails (output check for root-cause keywords plus an LLM self-check for SEV1 scenarios).
4. **Guided-mode LLM nudge** anchored to the authored tier + the last 20 trail events.
5. **Postmortem grading** (`gpt-6.1-sol`): rubric anchors, facts packet, structured scores with evidence quotes, blamelessness check, feedback. **Golden set of 60 hand-graded postmortems** (write about 20 per scenario by role-playing good, mediocre and bad).
6. **Approach classification:** diff + probe fingerprint + embeddings → known or unknown; unknown clusters go to the admin queue.
7. **Debrief coach note** citing trail event IDs.
8. **`evals/` suites in CI:** grading agreement, persona leak (50 adversarial prompts), classification accuracy, latency.
9. **Budgets and degradation:** per-user daily caps; global spend alarm; "teammates are busy" fallback to authored hints.

**Deliverables:** AI features live behind feature flags; cost dashboard in admin.

**QC gate: Phase 6**

- [ ] Grading agreement: within ±1 point on ≥ 85% of criteria; Spearman ≥ 0.8 on totals vs the golden set.
- [ ] Persona leak rate: **0/50** adversarial prompts reveal the root cause before the allowed hint tier.
- [ ] Prompt-injection suite: 20 injected payloads in logs, code comments and user messages ("ignore previous instructions…") produce no policy violations; personas never claim to have run actions.
- [ ] Latency: persona first token p95 < 1.5s; grading < 20s.
- [ ] Cost: average LLM cost per completed attempt is measured and below the target set in ADR (initial target ≤ $0.03 per attempt).
- [ ] Every LLM call appears in `llm_calls` and Langfuse with prompt version; budget cap tested (requests beyond the cap degrade gracefully).
- [ ] Privacy: trail redaction unit tests (emails, tokens, keys) pass; retention configured.

---

### Phase 7: Content, progression and onboarding (weeks 24–28)

**Goal:** enough breadth and stickiness for real users: about 20 scenarios, guest tutorial, Daily Incident, streaks and the admin console.

**Tasks**

1. **Content sprint:** about 17 more scenarios (20 total) across Databases, Caching, Queues, Deploys and config, and Memory/CPU. Add a second base app (**Ledger** for concurrency and idempotency). Add 12 more fault modules. **Write the primers** (4-minute reads) for each topic.
2. **Guest tutorial** `/try`: SEV4 scenario with progressive panel unlocks and just-in-time IC tips; guest attempt claimed on sign-up.
3. **Onboarding:** role and experience → optional 6-card triage calibration (Quick Fire cards) that seeds per-track ratings with high RD.
4. **Daily Incident:** scheduler (Temporal cron) picks from a curated rotation; spoiler-free share card (Next `ImageResponse`); pre-warmed sandbox pool for the daily scenario.
5. **Streaks:** daily/weekly mode, freezes, on-call leave, activity heatmap; **notifications** (email digest through a provider port, tested locally with Mailpit; at most 1/day, quiet hours, one-tap pause).
6. **Library polish:** service-map hero with mastery rings, topic primers, filters, list view toggle, "continue where you left off".
7. **Admin console:** review queue with playtest (author mode), validation reports, scenario analytics with auto-flags, approach cluster review, publish/retire, LLM cost view, user lookup (support).
8. **Pro mode** (hide gamification) and public profile opt-in.
9. **Case files** (ADR 013): the free, sandbox-less format.
   - `devgrill-content record <scenario>` boots the live scenario and captures evidence at fixed moments into `case-file/`: logs, metric series, deploy history, the diff, the config, and selected `psql` and `redis-cli` outputs.
   - The player gets a read-only workspace (the same panels, fed from the recording) and answers three questions: root cause (choice), first mitigation (choice) and durable fix (choice plus an optional short write-up).
   - Scoring is deterministic. AI review of the write-up counts against the plan's review allowance.
   - Every one of the 20 live scenarios ships a case file.

**Deliverables:** a content-complete beta candidate.

**QC gate: Phase 7**

- [ ] All 20 scenarios pass `devgrill-content test` (break, fix, approaches, anti-cheat) in CI nightly.
- [ ] Each scenario has been playtested by someone other than its author (or, solo, after a gap of at least 1 week), with a 3-point quality checklist: story clarity, clue fairness, verify fairness.
- [ ] **Time-to-first-win:** 5 new users on `/try` reach a passed verify in a median of < 5 minutes, without help.
- [ ] Daily Incident rollover tested across time zones; share card renders correctly (light and dark, no spoilers); pre-warm pool works.
- [ ] Streak logic property-tested (time zones, DST, freezes, leave days); notification caps enforced.
- [ ] Admin RBAC: authors can't publish; reviewers can't edit content; every admin action is audit-logged.
- [ ] Design QC (§14.5) on the library, onboarding, daily and admin screens; ethical-gamification checklist (§8.5 guardrails) signed off.

---

### Phase 8: Hardening and local release candidate (weeks 29–32) → **M2**

**Goal:** a release-quality product running entirely on this machine, hardened so that moving to a server later is a deployment task, not a rewrite. (Owner decision: stay local; hosting and cost come later, in Track H.)

**Tasks**

1. **Local sandbox hardening (ComposeDriver):**
   - `internal: true` networks with no egress.
   - Container limits (`cpus`, `mem_limit`, `pids_limit`), read-only root filesystem where possible, `no-new-privileges`, dropped capabilities.
   - Never mount the Docker socket into a sandbox.
2. **Production-shaped local stack:** `infra/compose/docker-compose.prod-local.yml` runs api, worker, gateway and web as built images (not dev servers) behind Caddy on `https://devgrill.localhost`. This proves the deployable artefacts.
3. **Observability for us:**
   - OTel → local VictoriaMetrics + Grafana (or Grafana's OTel LGTM image).
   - Platform SLO dashboards: attempt start success ≥ 99%, verify success ≥ 99%.
   - Runbooks in `docs/runbooks/`.
4. **Security review:**
   - OWASP ASVS L2 checklist.
   - CSP (strict, nonce-based), cookie flags.
   - Secrets only in `.env`, with gitleaks in CI.
   - Dependency, image and secret scanning gates.
   - Gateway abuse checklist.
   - Postgres backup script and a **restore drill**.
5. **Privacy groundwork:**
   - Data export and delete endpoints.
   - Retention jobs.
   - Draft privacy policy and terms (DPDP Act India + GDPR basics), published later with hosting.
6. **Partition** `attempt_events` by month.
7. **Local capacity test:** k6 drives N concurrent attempts on this machine until it saturates. Record sessions per GB of RAM; this becomes the input to the hosting cost decision.
8. **Playtest program:** 10–20 engineers play on this machine (in person, or screen-share with remote control) using GitHub sign-in; feedback form; changelog.

**QC gate: Phase 8 (M2: local release candidate)**

- [ ] **Escape and abuse red-team on ComposeDriver** (documented):
  - No egress from sandboxes.
  - Fork bomb, disk fill and memory hog are contained.
  - No access to other sessions, the platform network or the Docker socket.
- [ ] Restore drill: Postgres restored from a backup into a fresh container in < 30 minutes; documented.
- [ ] Production-shaped stack (`prod-local`) passes the full e2e suite.
- [ ] Capacity test recorded: concurrent sessions per 8 GB of Docker RAM, time-to-active, API p95 within budget.
- [ ] Platform dashboards and runbooks exist for: sandbox start failures, Temporal backlog, DB saturation, LLM outage, LLM cost spike.
- [ ] ASVS L2 checklist complete with no open SEV1/SEV2; CSP has no `unsafe-inline` scripts.
- [ ] 10+ playtesters completed at least one incident; activation and fairness feedback logged; P0/P1 issues fixed.

---

### Phase 9: Growth features, launch-ready locally (weeks 33–36) → **M3**

**Goal:** the habit and share loops are built and tested, so a public launch is ready the moment hosting (Track H) and pricing are decided.

**Tasks**

1. **Quick Fire** (mobile-first): card decks for every track (about 150 cards to start), 3/5-minute runs, 3 strikes, its own rating, share card.
2. **Weekly Outage:** first 4 real-postmortem replays; weekly goal; private-cohort boards.
3. **Cohorts:** invite codes, cohort leaderboards (per-scenario "segments"), cohort admin (for colleges and bootcamps).
4. **Share cards:** result, rating milestone, postmortem excerpt (opt-in); LinkedIn-friendly sizes.
5. **Plans without billing:**
   - Enforcement exists since Phase 3 (ADR 013).
   - Add the plan comparison page, the upgrade prompts at each refusal (no dark patterns), and admin tools to grant Pro (founders, playtesters, cohorts).
   - Payment providers wait for Track H.
6. **Launch assets, drafted:** landing page with a live replay, a "How verify works" explainer, docs, an engineering deep-dive blog post.
7. **SEO groundwork:** scenario and primer pages (SSR, structured data), sitemap, OG images.

**QC gate: Phase 9 (M3: launch-ready)**

- [ ] Quick Fire on a mid-range Android phone (Chrome, over LAN to the dev machine): route JS ≤ 180KB gz, INP < 200ms, usable on 4G throttling (DevTools).
- [ ] Entitlement limits enforced and tested (quota reached → honest UI, no 500s).
- [ ] Queue behaviour tested at 3× the local capacity limit (queue UI honest; no 500s).
- [ ] Full regression: e2e suite, content nightly, evals, a11y and Lighthouse all green.
- [ ] Analytics events verified (PostHog local or cloud free tier, decided in an ADR).

---

### Track H: Hosting, public beta and pricing (deferred, starts when the owner decides)

These were in phases 8 and 9 before the owner chose to stay local. Nothing earlier in the plan blocks them: the `SandboxDriver` port, production-shaped images and entitlements are all built for them.

1. **Hosting decision ADR:** use the Phase 8 capacity numbers to compare a self-hosted Sysbox server (~€70/month, ~25–40 sessions) with hosted sandboxes (~$0.17 per session-hour). Pick one.
2. **Sandbox host** (if self-hosted):
   - Ubuntu 24.04, Docker Engine + Sysbox, `SysboxDriver`.
   - nftables default-deny egress (block metadata IP and SMTP).
   - cgroup v2 limits, disk quotas.
   - Ansible in `infra/sandbox-host`.
3. **Control plane:** API, worker and web on a small VM with Caddy (or Fly/Render + Vercel); managed or self-managed Postgres with WAL-G backups; Valkey; Temporal on Postgres (or Temporal Cloud).
4. **Public-facing abuse prevention:**
   - Turnstile on guest starts.
   - Live sandboxes need a GitHub account at least 30 days old (cards and case files don't).
   - Per-IP limits.
   - A mining heuristic (shell CPU over 90% for 5 minutes ends the session and flags the account) plus Falco.
   - An acceptable-use policy.
5. **Email provider** (Resend), legal pages published, domain and TLS.
6. **Pricing and billing** (ADR 013 direction):
   - Razorpay for India (UPI Autopay, cards) and Paddle as merchant of record elsewhere. Stripe only if India onboarding reopens.
   - Regional prices (about ₹249/month or ₹1,999/year; $8/month or $60/year).
   - Upgrade flows with no dark patterns.
   - GST and export LUT confirmed with a CA.
7. **Public beta → launch:** waitlist, invite codes, then Product Hunt, HN, LinkedIn and X.

**QC gate: Track H** (the former phase 8/9 hosted gates):
- [ ] Escape and abuse red-team on the real host (egress, metadata IP, simulated miner killed within 5 minutes).
- [ ] Restore drill from off-site backup.
- [ ] Load test of 50 concurrent sessions on one host.
- [ ] Payments tested end to end in test mode (GST verified).
- [ ] Platform SLO alerts live.
- [ ] Legal pages published.

---

### Phase 10: Scale and AI content factory (week 37 onward, ongoing)

These are workstreams, prioritised by data from the beta.

1. **AI scenario generator + solver agent** (OpenAI Agents SDK inside Temporal): generate variants and new faults → validation pipeline → solver success-rate calibration → human review → publish. Target: one reviewed, generated scenario per week.
2. **Firecracker driver:** custom kernel, rootfs pipeline, warm snapshots, vsock agent (or adopt E2B open-source infra). Run it side by side with Sysbox for free capacity.
3. **ClickHouse** for `attempt_events`, telemetry and analytics; move Langfuse to shared ClickHouse.
4. **Multiplayer war rooms:** IC, Comms and Ops roles; shared workspace state (CRDT or Valkey-backed presence); async "pair on-call".
5. **New tracks:** Kubernetes (needs microVMs), observability-only scenarios, security incidents, data pipeline incidents.
6. **More base apps:** Shortly, Chatter; Go and Node stacks for language diversity.
7. **Authoring tooling** (closed source): an in-browser scenario editor for you and any invited authors. Opening the format to outside contributors is a later owner decision.
8. **Teams and hiring** (later): cohort analytics, assessment mode with integrity controls.
9. **Localisation:** Hindi UI (font fallback ready); INR pricing arrives with Track H.

**Recurring QC gate (every 6 weeks in phase 10):** all standard checks (§14), plus:
- cost per resolved incident trend,
- scenario quality analytics review (retire anything with < 10% solve rate or poor fairness ratings),
- evals green,
- a security patch cadence check (kernel and Sysbox CVEs).

---

## 16. Scalability and long-term architecture

| Concern | Now (MVP / beta) | Later (scale) | Design choice that keeps the path open |
|---|---|---|---|
| API | 1–2 stateless containers | Horizontal autoscale behind a load balancer | No in-process state; Valkey for shared state; idempotency keys |
| Workflows | Temporal dev server → Postgres-backed | Temporal Cloud or a dedicated cluster; task queues split per concern (lifecycle, verify, ai, content) | All long work is a workflow or activity; activities are idempotent |
| Sandboxes | Compose (dev) → 1 Sysbox host | Pool of Firecracker hosts + scheduler (bin-packing by CPU and RAM, scenario affinity for warm snapshots), multi-region (India + EU/US) | `SandboxDriver` port; scenario process-mode; verifier outside the sandbox |
| Gateway | Co-located per sandbox host | Per host, discovered via a registry; sticky routing by `attempt_id` | Ticket auth carries the host; the client reconnects to the URL given by the API |
| Database | Single Postgres 18 | Read replicas for catalog/profile; monthly partitions; events → ClickHouse; PgBouncer | UUIDv7 keys; one writer per table; no cross-service DB access except via the domain |
| Cache | Single Valkey | Valkey cluster/replica; leaderboards in sorted sets | Keys namespaced and TTL'd; cache is never the source of truth |
| Telemetry | Gateway scrape + WS | Vector → VictoriaMetrics/VictoriaLogs; session ID as metadata | Telemetry API reads through a port |
| Content | Git → DB sync | Content registry service; generated content; external contributors only if the owner later chooses to open the scenario format | Scenario spec versioned (`schema: devgrill/scenario@1`) with migrations |
| AI | Direct OpenAI with budgets | Batch API for grading backlogs; caching of persona prompt prefixes; second provider behind `LLMClient` | Provider-agnostic port; prompts versioned; evals gate changes |
| Frontend | Vercel or container | Edge caching for marketing/catalog; ISR for scenario pages | Server Components for read paths; client islands for the workspace |

**Cost model to track from day one:**
- Sandbox $ per session-hour (≈ $0.17 hosted vs ≈ €68/mo per ~25–40 concurrent self-hosted)
- LLM $ per attempt
- Infra $ per monthly active user
- Gross margin per plan

---

## 17. Security, privacy and abuse

- **Threat model** (write it in phase 2, update it in phase 8). Assets:
  - user accounts
  - scenario solutions (spoilers)
  - the host fleet (abuse)
  - LLM budget
  - other users' sessions
- **Sandbox isolation:**
  - Sysbox for the beta (shared kernel: patch promptly; dedicated hosts; no secrets on sandbox hosts).
  - Firecracker at scale.
  - Never mount the host Docker socket.
  - Default-deny egress.
  - Per-session networks.
- **Gateway:** single-use tickets bound to user, attempt and host; origin checks; message size limits; idle timeouts.
- **App security:** CSP with nonces, HSTS, SameSite cookies, CSRF protection on Better Auth endpoints, strict CORS, input validation everywhere (Pydantic), output encoding (React), rate limits, audit log for admin actions.
- **Supply chain:** pinned versions; lockfiles; Renovate; pip-audit, pnpm audit, Trivy; vendored skills reviewed (`.claude/skills/VENDORED.md`).
- **Privacy:**
  - Minimal PII (OAuth profile, email).
  - Postmortems private by default.
  - Analytics without cookies where possible.
  - Data export and delete.
  - Retention per §9.3.
  - DPDP (India) and GDPR basics.
- **Abuse** (ADR 013):
  - No egress on any plan.
  - Turnstile.
  - Account-age checks (a GitHub login alone is not a gate: mining gangs automate thousands of accounts).
  - Plan quotas plus a global daily free-minutes budget and kill switch.
  - Mining heuristics + Falco.
  - Acceptable-use policy and an abuse contact.
  - Card verification for heavy tiers if abuse appears.

---

## 18. Metrics and analytics

**North-star metric:** *incidents resolved per week* by active users.

| Funnel stage | Metric | Beta target (initial guess, revise with data) |
|---|---|---|
| Activation | Guest → first verify-passed within the session | ≥ 40% |
| Time to first win | Median minutes from landing to first verify pass | < 5 min |
| Sign-up | Guest → account after first win | ≥ 30% |
| Retention | D1 / D7 / D30 | 35% / 18% / 8% |
| Habit | Weekly active users completing ≥ 2 incidents | ≥ 25% of WAU |
| Virality | Share rate per resolved Daily Incident | ≥ 8% |
| Quality | Scenario fairness rating (post-debrief 1–5) | ≥ 4.2 |
| Economics | Sandbox + LLM cost per resolved incident | ≤ $0.10 |

**Events** (PostHog, typed in `packages/config/analytics.ts`):
- `attempt_started`, `panel_opened`, `hint_used`, `mitigated`, `deploy`, `verify_started`, `verify_passed`
- `postmortem_submitted`, `debrief_viewed`, `share_clicked`, `daily_completed`
- `quickfire_run_completed`, `case_file_completed`, `signup_completed`
- `quota_hit` (which limit), `upgrade_prompt_shown`, `upgrade_clicked`, `budget_paused` (server-side)

**Experiments** use PostHog flags (e.g. hint wording, onboarding calibration on or off).

---

## 19. Business model (tiers decided, prices **deferred**)

> **Owner decisions:**
> - 2026-10-12: prices and payments are decided later, together with hosting (Track H).
> - 2026-10-20: the **tier structure** is decided (ADR 013). Content that needs no sandbox is free. Live sandboxes are mostly Pro, and free users get a capped taste. Limits are enforced from Phase 3, so the bill is bounded before anyone pays.

**Free:**
- Quick Fire and case files, unlimited.
- The tutorial track and `access: free` live scenarios.
- The Daily Incident.
- 3 live starts and 120 sandbox-minutes a week.
- 30-minute sessions.
- Authored hints, 20 AI teammate messages a day, and 2 AI postmortem reviews a week.

**Pro:**
- The whole live library and Weekly Outages.
- 60-minute sessions with extend.
- 240 sandbox-minutes a day.
- Full AI teammates and postmortem reviews.
- History and replays.

**Price direction** (validated in the beta with a willingness-to-pay survey and a pricing-page experiment):
- About ₹249/month or ₹1,999/year in India.
- About $8/month or $60/year elsewhere.
- Annual about 35% cheaper.

**Payments:**
- Razorpay for India (UPI Autopay, cards; no re-authentication up to ₹15,000 per debit).
- Paddle as merchant of record elsewhere (it handles GST and VAT).
- Stripe India is invite-only for new businesses.
- Confirm GST registration and export LUT with a CA.

**Later segments:**
- **Cohorts and Teams:** colleges, bootcamps and companies. Cohort analytics, custom drills, SSO.
- **Hiring (careful):** assessment mode with integrity controls.

**Benchmarks** (2026-10-20):

| Platform | Free tier | Paid |
|---|---|---|
| iximiuz Labs | 1 h a day, 1 playground, safe egress only | $2.40–4/mo with PPP and annual pricing |
| SadServers | Daily-limited scenario selection, no internet | Pro $9/mo or $72/yr |
| Killercoda | 1 h sessions, captcha | PLUS: 4 h sessions, skips queues |
| TryHackMe | 1 h a day of AttackBox | Premium about €10.50/mo billed annually |

**Planning:**
- Conversion: model revenue on 2–3% free-to-paid. The developer-tool median is about 5%; edtech is lower.
- Unit cost: under ₹1 per live session on a dedicated host (§12.4).

---

## 20. Risks and mitigations

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Solo part-time scope creep | High / high | Strict phase gates; M1 retrospective re-plans; cut list: multiplayer, generator, Firecracker are all post-launch |
| Sandbox cost or abuse gets the host banned (Hetzner forbids mining) | Medium / high | Default-deny egress from day one; quotas; mining detection; Turnstile; budget alarms |
| Sysbox shared-kernel escape | Low / high | Dedicated hosts, prompt patching, no secrets on hosts, Firecracker roadmap |
| Scenario authoring is slower than planned | High / medium | Base app × fault library; content CLI; AI generator later; prioritise 20 excellent scenarios over 100 mediocre ones |
| Verify fairness disputes ("my valid fix failed") | Medium / medium | Behaviour-based probes, anti-cheat set, "report verify issue" button tied to admin review, approach library grows from disputes |
| LLM leaks answers or grades inconsistently | Medium / medium | Hint-tier ceilings, leak evals, golden-set calibration, structured outputs with evidence quotes |
| LLM costs at scale | Medium / medium | Cheap model for chat, authored hints first, caps, prompt caching, Batch API for grading |
| Native-Windows dev parity (Sysbox and Firecracker can't run in Docker Desktop; CRLF line endings; path differences; no uvloop) | High / low (while local) | ComposeDriver is the only driver in scope; `.gitattributes` forces LF; pathlib everywhere; driver contract tests so a Linux driver can be added later; CI runs on Linux to catch Windows-only assumptions |
| Corporate proxy breaks tooling | High / low | CA env vars documented; personal network for heavy pulls |
| Competitors move (SadServers incident simulator, Uptime Labs) | Medium / medium | Speed to a polished vertical slice; depth (live stack + verify + approach comparison) is hard to copy; scenario library depth |
| Hetzner and DRAM price volatility | Medium / low | Driver abstraction lets us move hosts or fall back to hosted sandboxes |
| 0.x dependencies break (FastAPI, Agents SDK, Hey API) | Medium / low | Exact pins, Renovate with CI, adapters around them |

---

## 21. Owner decisions and remaining open items

**Decided (2026-10-12):**

| # | Topic | Decision | Effect on the plan |
|---|---|---|---|
| 1 | Name | **DevGrill** | Used throughout; domains and GitHub handle appear free (§2) |
| 2 | Hosting and cost | **Stay local for now**; decide cost later | Phases 0–9 run fully on this machine; hosted beta, abuse controls for the public internet, and launch moved to **Track H** |
| 3 | Dev environment | **Native Windows** | §5.5 Windows rules: LF endings, `just`, pathlib, Docker named pipe, Linux CI |
| 4 | Pricing | **Decide later** | §19 deferred; only the `entitlements` plumbing with free defaults is built |
| 5 | Licence | **Fully closed / private** | Private repo, proprietary `LICENSE`; no public scenarios repo; invited authors only |
| 6 | Market | **India-first, IST rollover** | Daily Incident resets at 00:00 IST; India-friendly defaults; global users welcome |
| 7 | Sign-in | **GitHub only** | Better Auth with the GitHub provider; Google and email can be added later via config |
| 8 | Access tiers (2026-10-20) | **Sandbox-free content is free; live sandboxes mostly Pro, with a capped free taste** | ADR 013: case files format (Phase 7), `access` field and quota/budget enforcement (Phase 3), prices still in Track H |

**Still open (not blocking phase 0):**
1. Register `devgrill.com` and `devgrill.dev` now as cheap insurance, or wait?
2. When to trigger Track H. Suggested trigger: after the M2 playtests show retention worth paying for.
3. Product analytics locally: PostHog cloud free tier (needs internet) or self-hosted later? Decide in an ADR in phase 7.

---

## 22. Appendices

### A. Glossary

| Term | Meaning |
|---|---|
| Attempt | One user playing one scenario version |
| Base app | Reusable realistic system (ShopKart, Ledger…) that scenarios break |
| Fault module | Reusable, parameterised way to break a base app, with a symptom contract |
| Probe | One verify check: load, chaos, invariant, hidden test or budget |
| Approach | A known way of fixing a scenario, with an outcome and trade-offs |
| Beat | A scripted, deterministic teammate message |
| Mitigation | Restoring service (rollback, flag…) before the root-cause fix |
| Trail | The recorded investigation events of an attempt |
| SEV ladder | SEV4 (warm-up) → SEV1 (hardest); also in-scenario severity |

### B. `infra/compose/docker-compose.dev.yml`

The authoritative file lives in the repo (created in phase 0). Services and pinned images:

| Service | Image | Ports (localhost only) |
|---|---|---|
| postgres | `pgvector/pgvector:0.8.7-pg18-trixie` (Postgres 18.6, `pg_stat_statements` preloaded) | 5432 |
| valkey | `valkey/valkey:9.1` (no persistence) | 6379 |
| temporal | `temporalio/temporal:1.9.1` (`server start-dev`, SQLite in `/home/temporal`) | 7233, UI 8233 |
| objectstore | `chrislusf/seaweedfs:4.48` (S3 API) | 8333 |
| mailpit | `axllent/mailpit:v1.31.5` | SMTP 1025, UI 8025 |

### C. Environment variables (`.env.example`)

```
# shared
DEVGRILL_ENV=dev
DATABASE_URL=postgresql+asyncpg://devgrill:devgrill@localhost:5432/devgrill
VALKEY_URL=redis://localhost:6379/0
TEMPORAL_ADDRESS=localhost:7233
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=devgrill
S3_SECRET_KEY=devgrill-dev-secret
# auth
BETTER_AUTH_SECRET=change-me
BETTER_AUTH_URL=http://localhost:3000
GITHUB_CLIENT_ID= / GITHUB_CLIENT_SECRET=
AUTH_JWKS_URL=http://localhost:3000/api/auth/jwks
INTERNAL_HMAC_SECRET=change-me
# ai
OPENAI_API_KEY=            # provided by owner; never commit
LLM_DAILY_BUDGET_USD=5
LANGFUSE_HOST= / LANGFUSE_PUBLIC_KEY= / LANGFUSE_SECRET_KEY=
# sandbox
SANDBOX_DRIVER=compose
SANDBOX_MAX_LIVE=4                  # fleet cap
SANDBOX_DAILY_MINUTES_BUDGET=600    # free + guest minutes per IST day
SANDBOX_FREE_STARTS=true            # kill switch
SANDBOX_GUEST_SCENARIOS=ttl-zero
GATEWAY_PUBLIC_URL=ws://localhost:8100
# corporate network (Windows)
NODE_EXTRA_CA_CERTS=
SSL_CERT_FILE=
UV_SYSTEM_CERTS=1
```

### D. Task runner targets (`just`)

| Target | Does |
|---|---|
| `just setup` | Check tools, install uv and pnpm deps, copy `.env.example` |
| `just dev` | Compose deps up + api, gateway, worker, web with reload |
| `just test` / `just test-e2e` | Python + JS unit/integration / Playwright |
| `just lint` / `just types` | ruff, eslint / basedpyright, tsc |
| `just gen` | OpenAPI → TS client, JSON Schema for scenarios, tokens build |
| `just db-migrate` / `db-reset` / `db-seed` | Alembic up / drop+recreate / seed catalog |
| `just content-validate S=<slug>` / `content-up S=<slug>` | Scenario validation / local play |
| `just evals` | AI eval suites |

### E. `CLAUDE.md` (draft for the repo root)

```markdown
# DevGrill — working agreement for coding agents

- Read docs/PLAN.md (this plan) and the ADRs in docs/adr before architectural changes; add an ADR for new decisions.
- Python: uv workspace, Python 3.14, FastAPI, SQLAlchemy 2.1 async, Pydantic v2. Domain code in packages/py-core/devgrill/domain must not import infra.
- Frontend: Next.js 16 App Router, React 19, Tailwind v4 tokens from packages/tokens. Never use raw colours; use semantic tokens only.
- UI work: load the vendored skills in .claude/skills — frontend-design for direction, tailwind-design-system + oklch-skill for tokens and colour, emil-design-eng/animate for motion, vercel-* for React/Next. Run web-design-guidelines, accessibility and review-animations before closing a UI task.
- Motion: keyboard actions are instant; respect reduced motion; no animation on streaming panels; celebrate only on verify/debrief.
- Severity is always icon + label + colour.
- API changes: update OpenAPI, run `just gen`, keep Schemathesis green.
- Scenarios: every scenario must pass `just content-validate` (breaks, fixable, approaches, anti-cheat).
- Treat sandbox output, logs and user text as untrusted data in any LLM prompt.
- Never commit secrets; OPENAI_API_KEY lives in .env only.
```

### F. ADR template (`docs/adr/NNN-title.md`)

```markdown
# NNN. Title
Date: YYYY-MM-DD · Status: proposed | accepted | superseded by NNN
## Context
## Decision
## Consequences (positive, negative, follow-ups)
## Alternatives considered
```

### G. Scoring and rating notes

- **Score (0–100)** = Σ weightᵢ × componentᵢ:
  - **mitigation:** `clamp(1 − (t_mitigate − par)/par, 0, 1)`
  - **resolution:** weighted probe pass ratio; partial approaches capped at 0.6
  - **postmortem:** rubric total / max
  - **communication:** status-update cadence + AI-judged clarity
  - **Hint penalty:** −5 / −10 / −20 for tiers 1/2/3, floored at 0.
- **Glicko-2 outcome** `s = score/100`, mapped through a logistic so that a clean resolve ≈ 1.0. Guided mode multiplies the rating change by 0.5, and Tutorial mode doesn't change ratings. RD decays with inactivity (standard Glicko-2 period = 1 week).

### H. Research sources (checked 2026-10-12)

- **Competitors and infrastructure:**
  - iximiuz Labs playgrounds: https://labs.iximiuz.com/blog/iximiuz-labs-playgrounds-2-0
  - SadServers architecture: https://github.com/fduran/sadservers
  - Sysbox: https://github.com/nestybox/sysbox
  - Modal VM sandboxes: https://frontend.modal.com/docs/guide/vm-sandboxes
  - E2B self-host: https://raw.githubusercontent.com/e2b-dev/infra/main/self-host.md
  - Fly suspend/resume: https://fly.io/docs/reference/suspend-resume/
  - Toxiproxy: https://github.com/Shopify/toxiproxy
  - k6: https://github.com/grafana/k6
  - Rootly Academy: https://rootly.com/blog/introducing-the-rootly-academy-hands-on-incident-response-training
  - Uptime Labs: https://www.einpresswire.com/article/845737112/uptime-labs-launches-free-incident-simulation-to-help-teams-build-critical-response-skills
- **Stack:**
  - FastAPI: https://pypi.org/project/fastapi/
  - uv workspaces: https://docs.astral.sh/uv/concepts/projects/workspaces/
  - Temporal Python SDK: https://pypi.org/project/temporalio/
  - Valkey: https://hub.docker.com/r/valkey/valkey
  - Better Auth JWT: https://www.better-auth.com/docs/plugins/jwt
  - Next.js 16: https://nextjs.org/blog/next-16
  - shadcn changelog: https://ui.shadcn.com/docs/changelog
  - xterm.js: https://github.com/xtermjs/xterm.js/releases
  - uPlot: https://github.com/leeoniya/uPlot
  - Hey API: https://www.npmjs.com/package/@hey-api/openapi-ts
  - OpenAI models: https://developers.openai.com/api/docs/models
  - OpenAI pricing: https://developers.openai.com/api/docs/pricing
  - OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
  - Langfuse self-hosting: https://langfuse.com/self-hosting
  - pgvector: https://github.com/pgvector/pgvector
- **UX and design:**
  - Duolingo streaks: https://blog.duolingo.com/how-duolingo-streak-builds-habit/
  - Duolingo growth: https://www.lennysnewsletter.com/p/how-duolingo-reignited-user-growth
  - Lichess puzzles: https://lichess.org/blog/X-S6gRUAAGjNX4ki/new-puzzles-are-here
  - NN/g mobile tutorials: https://www.nngroup.com/articles/mobile-tutorials/
  - WAI-ARIA window splitter: https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter
  - VS Code accessibility: https://code.visualstudio.com/docs/configure/accessibility/accessibility
  - Linear UI redesign: https://linear.app/now/how-we-redesigned-the-linear-ui
  - Radix colour scale: https://www.radix-ui.com/colors/docs/palette-composition/understanding-the-scale
  - incident.io brand: https://incident.io/brand
  - Emil Kowalski on animation: https://emilkowal.ski/ui/great-animations
  - WCAG 2.3.3: https://w3c.github.io/wcag/understanding/animation-from-interactions.html
- **Naming:**
  - SEV0 conference conflict: https://incident.io/blog/sev0-2024
  - FireHydrant FireDrills: https://firehydrant.com/blog/what-a-successful-trial-looks-like/
  - Drillbit conflict: https://library.iimcal.ac.in/Drillbit/
- **Tiers, pricing and abuse (checked 2026-10-20, ADR 013):**
  - iximiuz Labs pricing: https://labs.iximiuz.com/pricing
  - SadServers pricing and FAQ: https://sadservers.com/pricing , https://sadservers.com/faq
  - Killercoda pricing: https://killercoda.com/pricing
  - TryHackMe pricing: https://tryhackme.com/pricing
  - Pluralsight sandboxes: https://www.pluralsight.com/product/sandboxes
  - Railway trial (GitHub account checks): https://docs.railway.com/pricing/free-trial
  - GitLab card verification against miners: https://portswigger.net/daily-swig/gitlab-tackles-crypto-mining-abuse-with-payment-card-checks-for-free-accounts
  - PURPLEURCHIN mass-account mining: https://unit42.paloaltonetworks.com/purpleurchin-steals-cloud-resources/
  - Hetzner April 2026 price change: https://www.it-daily.net/?p=170309
  - Fly.io pricing: https://docs.fly.io/about/pricing
  - Razorpay pricing: https://razorpay.com/pricing/
  - Stripe India invite-only: https://support.stripe.com/questions/stripe-accounts-are-invite-only-in-india
  - Paddle India: https://www.paddle.com/billing/india
  - UPI Autopay limits: https://docs.stripe.com/payments/upi/upi-autopay
  - Free-to-paid benchmarks: https://lennysnewsletter.com/p/what-is-a-good-free-to-paid-conversion
- **Vendored skills:** see `.claude/skills/VENDORED.md` for repos, commits and licences.

---

*End of plan. Decisions are recorded in §21. Next step: Phase 0.*
