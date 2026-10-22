# Phase 5 QC report: verify engine, scoring, debrief and ratings (M1)

Date: 2026-10-21 · Result: **PASS (M1 reached)**; the owner reviews the demo capture (see "Owed") · Decision: ADR 015. Red team: `docs/qc/phase-5-red-team.md`. Numbers: `docs/perf/phase-5.md`. Retrospective: `docs/qc/m1-retrospective.md`.

## What was built

- **`VerifyRun`**, a child workflow of the attempt's lifecycle:
  - **begin:** freeze the incident and open the run;
  - **probes:** one activity per probe group, load probes that share a replay running together;
  - **finish:** decide the outcome, record the verdict, resolve or go back to the incident.

  Each probe streams progress (`verify_progress`) and stores its result. A JSON artifact per probe goes to object storage. Asking again while a run is in progress returns that run.
- **The verifier, rebuilt around trusted measurement:**
  - **Measured by the platform:** k6's client-side numbers, Postgres's core statistics through the read-only role (`db_scans_per_request`), the platform's exporters, and chaos recovery computed from k6's per-request CSV (`dg-recovery`).
  - **Telemetry checked:** a standard honest-metrics probe compares the app's telemetry with k6.
  - **Hidden tests:** decided by exit code.
  - **Fail closed:** statistics resets, refused flushes and removed toxics fail the probe.
- **ShopKart's database roles:** `postgres` is a platform-only superuser with a random password. The app and the player use `shopkart`, which owns the tables but isn't a superuser. The stats extension lives in a `monitor` schema the player can't touch.
- **Anti-cheat:** every published playable scenario needs a `hidden_test` (schema rule). ShopKart's standard `base/correctness.py` checks products against the database, 404s, search, orders, and price changes on hot and cold products.
- **Approaches and cheats as content:** `approaches/*.yaml` with runnable steps, declared outcomes and a `match` rule. 8 known approaches and 8 cheats across the three scenarios. `devgrill-content test --approaches` runs them all; CI runs them nightly, one job per scenario.
- **Scoring:** mitigation time vs par, resolution, communication and hints, plus the pending postmortem. The **incident score** drives ratings. Mitigation counts once verify has measured the recovery from outside.
- **Ratings:**
  - Glicko-2, player vs scenario, settled once after teardown (`attempt.settle`, idempotent);
  - bounded at ±120, guided gains halved;
  - guests, tutorials, our failures and early "wrong scenario" exits are not rated;
  - also written: rating history, scenario ratings, the activity day and the streak.
- **Debrief API and page:**
  - score, rating change and track mastery;
  - the best run's probes with targets;
  - the investigation replay with authored markers (key clues, lost time) and hints;
  - known approaches with shares and yours marked, only once resolved;
  - next drills.

  The demo debrief renders the same component with canned data.
- **Postmortem editor v1:** four sections, autosaved as a draft, submitted once with the timeline from the trail added. Ungraded until phase 6.
- **Workspace:** the verify dialog shows each probe queued, then running, then passed or failed. Every ended incident links to its debrief.

## Gate checklist (docs/PLAN.md, Phase 5)

| # | Gate item | Result | Evidence |
|---|---|---|---|
| 1 | Each scenario: reference fix passes verify; each known approach gives its declared outcome; each cheat fails (automated) | ✅ | ttl-zero: reference, 2 approaches, 4 cheats. pool-party: reference, 3 approaches (one `fails`), 1 cheat. big-sale-meltdown: reference, 3 approaches (one `partial`), 3 cheats. All give their declared outcome. One declaration was wrong and corrected: `bigger-pool` fails on latency, not connection headroom. Reports in `content/.reports/`; the CI `break-fix` matrix runs nightly | `devgrill-content test <slug> --approaches` (reports in `content/.reports/`); CI `break-fix` matrix, nightly |
| 2 | Verify is tamper-proof: a red-team checklist of 10 attempts, documented | ✅ | `docs/qc/phase-5-red-team.md`: 10 attempts, each failing verify or refused, as cheats in real sandboxes, verifier unit tests or checks against the built image |
| 3 | Verify < 4 minutes per scenario; progress visible throughout; re-running is idempotent | ✅ | Reference verify: 50.8 s, 49.6 s and 91.6 s. Slowest of all 19 runs: 116.5 s (`docs/perf/phase-5.md`). The dialog shows each probe queued, running, then decided. Idempotency is covered by `test_verify_is_idempotent_while_running` and `test_verify_runs_are_numbered_and_requests_during_a_run_are_absorbed` | Durations in `docs/perf/phase-5.md`; progress from `verify_progress` events in the dialog; `test_verify_is_idempotent_while_running`, `test_verify_runs_are_numbered_and_requests_during_a_run_are_absorbed` |
| 4 | Scoring and Glicko property tests: monotonic in mitigation time, hints never increase the score, deltas bounded with the right sign | ✅ | `packages/py-core/tests/test_scoring.py` (Hypothesis): bounds, slower mitigation never scores more, hints never raise it, more resolution never lowers it, deltas bounded and signed, guided gains at most half, better results never rate lower. It caught one real bug: the bound was applied after the guided halving |
| 5 | E2E: the full loop to the debrief, in CI nightly | ✅ | `apps/web/e2e/live-flow.mjs` passes locally: 3 min 33 s, verify 55 s, then the debrief and a submitted postmortem. It runs nightly in CI's `workspace` job. The first run found a real bug that unit tests with fake activities missed: storing results threw. It's fixed, and covered by `apps/worker/tests/test_verify_activities.py` against real Postgres | `apps/web/e2e/live-flow.mjs` in the `workspace` job (`.github/workflows/content.yml`, nightly). It covers start, terminal and reload, CLI, logs, charts, rollback, mitigated, editor fix, verify, debrief and postmortem |
| 6 | Debrief celebration skippable and off under reduced motion; accessible headings and table semantics | ✅ | The keyboard e2e drives the demo debrief, now the live component: OS reduced motion, the in-app setting and full motion. Axe on `/incident/demo/debrief` and `/postmortem`. One h1, h2 sections, the probe table and the score table with captions and header scopes |
| 7 | M1 demo: a 5-minute capture of the full loop, and a retrospective | ✅ (owner review owed) | Captured locally (`apps/web/test-results/video/`, 3.5 minutes, not committed: 22 MB). `docs/qc/m1-retrospective.md` | `RECORD=1 node apps/web/e2e/live-flow.mjs` saves the capture (`apps/web/test-results/video/`); `docs/qc/m1-retrospective.md` |

**Standard checks:**
- ruff and basedpyright clean;
- unit tests: 171;
- integration tests (real Postgres and Valkey, including Schemathesis on the new endpoints);
- web typecheck, lint, Prettier and colour check;
- axe and keyboard e2e;
- `devgrill-content validate` (patches of approaches and cheats included);
- LF line endings;
- OpenAPI client regenerated.

**Design:** screenshots of the debrief and postmortem in light and dark, at 1440 and 390 px, are in `docs/design/qc/phase-5/`. Axe on the demo debrief (now the live component) found two sideways-scrolling regions keyboard users couldn't reach: the probe table and the approach's code block. Both are now focusable, labelled regions.

## Defects found and fixed during the phase

1. **Two probe targets trusted the app's own metrics** (`cache_hit_rate`, `db_qps_product`): the player can make them say anything. They are replaced by Postgres-measured database work, and validation now refuses app-reported metrics in probe targets.
2. **The player was the database superuser** and could reset statistics, replace the stats extension, or shadow the catalog. The role is split: superuser `postgres` for the platform, owner `shopkart` for the app and the player.
3. **Chaos recovery came from the app's metrics.** It now comes from k6's per-request results.
4. **`redis-cli` exits 0 on refused commands**, so a blocked FLUSHALL looked like success. The answer is now checked.
5. **Glicko bound vs guided halving** (Hypothesis): bounding after halving let a guided gain exceed half the on-call one. Now the bound comes first.
6. **A cheat patch that crashed the API "passed"** (failed verify for the wrong reason). A cheat's patch must now deploy; only its commands may be refused.
7. **Storing probe results threw in the real worker** (`dict()` of a SQLAlchemy result). The first live run caught it. The run reported "couldn't finish, doesn't count" as designed, and probes that never ran now show "Not run" rather than "Fail".
8. **The debrief replay** showed `-00:00` for the page and full 40-character SHAs for rollbacks.

## Deviations

- **"Hidden tests"** are behavioural checks run from the probe container (HTTP plus the read-only database), not unit tests inside the player's service. Code the player controls can't decide a probe.
- **Approach recognition** is rule-based (`match` in `approaches/*.yaml`) until phase 6's classifier. Shares count resolved attempts per recognised approach.
- **The postmortem** has four fixed sections plus the timeline. Rubric-based grading arrives in phase 6, and the score shows it as pending.
- **Toxic-based chaos** isn't used by the three scenarios. Its tamper check is unit-tested; the network split that stops an app bypassing Toxiproxy comes with the first such probe.

## Follow-up found by CI

- **big-sale-meltdown's latency page was hardware-sensitive.** On fast CI runners Postgres absorbed the cache misses, so p99 sometimes stayed under 500 ms and the reference run reported "the scenario does not break as declared" (push run on c55215d; the nightly on the same commit passed). **Fixed on 2026-10-22:** the scenario's SLO adds `cache_hit_rate > 0.5`. That is what this incident breaks (0.0 broken, about 0.8 fixed), whatever the hardware. Latency and errors still have to recover for mitigation. On a fast machine the page title ("p99 > 1.5s") can overstate the latency the player sees; calibrating load to the sandbox's CPU is a hosting item (Track H).

## Owed by the owner

- Watch the M1 capture and confirm the loop reads well end to end.
- Carried over from phase 4: an NVDA pass and 3 usability sessions. (`/review-animations` ran on 2026-10-22; its findings are fixed.)
