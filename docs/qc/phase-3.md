# Phase 3 QC report: Scenario engine v1

Date: 2026-10-20 · Result: **PASS with recorded deviations** (see "Deviations"). Decisions: ADR 012 (spec v1, fault contract, local sandbox), ADR 013 (access tiers and the sandbox budget). Numbers: `docs/perf/phase-3.md`.

## What was built

- **ShopKart v1** (`content/base-apps/shopkart`). Services:
  - an API with 4 uvicorn workers, multiprocess Prometheus metrics, route-template labels, config-as-code in `config/app.env`, and a reviews-backed rating summary;
  - an orders worker;
  - Postgres 18, pre-seeded in its image with 18k products, 50k orders and 300k reviews;
  - Valkey;
  - Toxiproxy, with `postgres`, `postgres-dr` and `redis` proxies;
  - postgres and redis exporters;
  - a `tools` shell with psql, redis-cli, git, tmux and the `devgrill` CLI;
  - a k6 load profile.
- **Spec v1** (Pydantic, exported as JSON Schema by `devgrill-content schema`): base app, scenario, fault, solution and approach, plus `access` (ADR 013).
- **Eight fault modules:** `cache/key-format-change`, `cache/ttl-zero`, `db/missing-index`, `db/pool-exhaustion`, `db/lock-migration`, `queue/poison-message`, `mem/leak-accelerated`, `config/bad-env`. Each declares its mechanism, typed params and a symptom contract.
- **The sandbox layer** (`devgrill.sandbox`):
  - the driver protocol;
  - `ComposeDriver` on the Docker Engine API;
  - the platform-owned probe container;
  - the metric evaluator;
  - the verifier (load, chaos, invariant and budget probes);
  - the content loader with its cross-checks;
  - content-addressed image builds.
- **Temporal `SandboxLifecycle`:**
  - provision, then active;
  - timers for faults due after T, the TTL and the idle timeout;
  - signals: abandon, reset (at most 3), extend (per plan), verify, touch;
  - teardown in `finally`.
  - The activities write states, sessions (`cpu_seconds`, `est_cost_usd`) and `attempt_events`, and announce new events on Valkey.
- **API:**
  - `POST /v1/attempts`, `GET`, `DELETE`, `/extend`, `/reset`, `/verify`;
  - `/events` (SSE, resumable with `Last-Event-ID`);
  - `GET /v1/me/usage`.
  - Every start goes through the ADR 013 policy: plan access, one live sandbox, starts and minutes quotas, the fleet cap, and the daily free-minutes budget with its kill switch.
  - Migration 0003 adds `scenarios.access`.
- **Content CLI** (`devgrill-content`): `validate` (no Docker; checks that patches apply), `schema`, `build`, `up`, `test`, `publish`/`seed`, `sandboxes --sweep`.
- **Three scenarios, fully authored:**
  - ttl-zero (free, the tutorial candidate);
  - pool-party (free);
  - big-sale-meltdown (pro).
  - Each has a page, faults, a load, an SLO, probes, hints, a rubric, deploy history, beats and a reference solution. The other nine stay `playable: false`.
- **Plan and approach** (owner request, 2026-10-20):
  - research on lab-platform tiers, abuse and costs;
  - ADR 013 and PLAN §12.4, §17, §19, §21, Phase 3/7/9/Track H updated;
  - case files planned as the free, sandbox-less format (Phase 7).

## Gate checklist (docs/PLAN.md §15, Phase 3)

| # | Gate item | Result | Evidence |
|---|---|---|---|
| 1 | `devgrill-content test` passes for all 3 scenarios: symptoms within 60 s, and the reference fix passes all probes | ✅ | SLO breached after 7.5 s (ttl-zero), 5.7 s (pool-party), 7.9 s (big-sale-meltdown); every symptom contract met; every probe passes after the fix (`docs/perf/phase-3.md`, `content/.reports/`). CI: `.github/workflows/content.yml` (on content changes, nightly, on demand) |
| 2 | 50 sequential create→destroy cycles, 0 leaked containers, networks or volumes | ✅ | `scripts/sandbox_gate.py leaks -n 50`: 0 containers and 0 networks before and after. The one extra host volume was traced to a manual test, not a sandbox (see perf doc). Repeated with the baked image (10 cycles): nothing left |
| 3 | Killing the worker mid-provision still ends in a clean teardown | ✅ | **Real stack:** `scripts/attempt_e2e.py crash` hard-kills the worker process with 3 containers up. A new worker re-provisions from a clean slate, the attempt goes active, is abandoned, and is torn down with 0 leftovers. **Workflow:** `test_worker_crash_mid_provision` (dev Temporal) |
| 4 | Temporal time-skipping tests: TTL expiry, idle, abandon, reset, worker crash | ✅ | `apps/worker/tests/test_sandbox_lifecycle.py` (12 tests): TTL (30 min), idle with touch (ends about 8 min after the last touch), abandon, reset (limited to 3, deadline kept), extend (granted up to the plan, the third refused), verify pass and fail, faults due after T in order, provision failing for good (teardown still runs), provision retry, cancellation, worker crash |
| 5 | No egress; the platform network is unreachable | ✅ | `scripts/sandbox_gate.py isolation`: example.com and 1.1.1.1 fail; the host and every platform container IP are unreachable from the shell |
| 6 | Time to active < 45 s, recorded in `docs/perf/phase-3.md` | ✅ | p50 26.2 s, max 27.6 s (driver); 34.0 s through API, Temporal and the worker |
| 7 | Fork bomb contained by `pids_limit`; a memory hog OOMs only its own container | ✅ | `isolation`: the bomb fills the shell's 512 pids and the API keeps serving; 2 GiB in a 512 MiB shell exits 137 and the API keeps serving |
| 8 | ADR for the fault-module contract and the scenario spec v1 | ✅ | ADR 012; ADR 013 for tiers |
| 9 | (ADR 013, added) Entitlement policy unit-tested; the API refuses with problem+json and starts no sandbox | ✅ | `packages/py-core/tests/test_entitlements.py` (17): every refusal, IST rollover, the Daily exception, guests, TTL capped by the minutes left. `apps/api/tests/test_attempts.py` (15, real Postgres and Valkey): 403 `upgrade_required` and `sign_up_required`, 409 `active_attempt_exists`, 429 `quota_exceeded` with `Retry-After`, 503 `capacity` and `budget_paused`; Pro unaffected by the free budget; ownership 404; SSE until teardown, resumable |

**Standard checks:**
- ruff and basedpyright clean;
- unit tests: 120;
- integration tests: 58 (including Schemathesis on the new endpoints, with a null orchestrator);
- `devgrill-content validate`: 12 scenarios, 0 problems;
- web typecheck; LF line endings;
- OpenAPI client regenerated.

## Defects found and fixed during the phase

1. **p99 was never measurable.** The API labelled latency by raw path, because the route is unknown before routing. That is unbounded cardinality, and the route regex never matched. It now labels by template, after `call_next`.
2. **Metrics described one worker in four.** Prometheus counters weren't shared across uvicorn workers, so each scrape saw a random worker. It now uses multiprocess mode, with the directory cleared at start.
3. **The key-format-change fault produced no lasting incident.** Prefixing reads and writes alike just refilled the cache. The patch is now the realistic refactor bug: reads use the versioned key and writes don't.
4. **Pool exhaustion through raw latency wasn't fixable by the player.** It is now a config deploy to a cross-region endpoint (Little's law). Enlarging the pool is a natural trap.
5. **Uncached reads were too cheap to make incidents real.** A product read now includes a rating summary over 300k reviews, so caching matters at sale scale.
6. **YAML 1.1 reads the key `on:` as `true`.** Beats now use `when:`.
7. **Stored specs couldn't be read back.** `model_dump` writes field names and validation expected aliases. The spec models now accept both.
8. **k6 v2 dropped `--no-summary`.**
9. **SSE sent Python reprs, not JSON.**
10. **Teardown read container stats serially, about a second each.** It now uses one-shot stats in parallel. Before the fix, the e2e script killed the worker mid-teardown; the next worker finished it, which proved the guarantee by accident.
11. **Ruff formatting the base app could silently break fault patches.** `validate` now checks that every patch applies.

## Deviations

- **The in-sandbox `devgrill` CLI** (status, logs, restart, deploy, rollback) has no control endpoint yet: the gateway is Phase 4. Inside a sandbox it reports "control plane unreachable". The driver already has deploy, rollback (a deploy at a ref) and restart.
- **Mitigation detection while playing** (the SLO holding for `for_s`, then `state:mitigated`) runs in `devgrill-content test`, not yet in the workflow. Telemetry streaming is Phase 4. Beats are specified but not yet emitted.
- **Hidden-test probes, scoring, approaches outcomes and anti-cheat runs** are Phase 5. The verifier skips hidden tests, and none of the three scenarios use them.
- **Content is loaded from the `content/` folder** by slug at provision time, not from the pinned `scenario_versions` row. That is fine locally. Hosted (Track H) needs versioned bundles and image digests.
- **Queueing** ("You're #3") is not built. Above the fleet cap, starts get `503 capacity` with `Retry-After`.
- **The daily-challenge picker** can choose a `playable: false` scenario. The Phase 7 scheduler will restrict it to playable ones.
