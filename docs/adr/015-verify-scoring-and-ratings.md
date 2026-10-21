# 015. Verify, scoring and ratings (phase 5)

Date: 2026-10-21 · Status: accepted

## Context

Phase 5 closes the loop: verify decides whether a fix holds, the attempt gets a score and a
rating change, and the debrief explains what happened. Verify is what the rating stands on, so
it has to be right and hard to fool.

The player has root in the shell container, edits and deploys the API, and runs SQL. Before this
phase they also held the database superuser. Phase 3's verifier read two of its targets from the
API's own metrics, which the player can make say anything.

## Decisions

### Verify runs as a child workflow, one activity per probe group

`VerifyRun` (`apps/worker/src/devgrill_worker/verify_run.py`) is started by `SandboxLifecycle`,
one per request, with ids `verify-<attempt>-<n>`. It has three steps:
1. **begin:** freeze the incident (stop the load), open the `verify_runs` row and announce the
   probes.
2. **probes:** one activity per probe group, each storing its results and streaming progress
   (`verify_progress` events) as it lands.
3. **finish:** decide the outcome (passed, partial, failed or error), record the `verify` event,
   and resolve the incident or go back to it.

Why this shape:
- **Grouping:** load probes that share a script and a multiplier share one replay, so a scenario
  verifies in about 1–2 minutes.
- **Retries:** a crashed worker repeats only the group it was running.
- **Our failures don't count:** a group that fails on our side (Docker, the probe container)
  makes the run an error, which doesn't count against the player.
- **Idempotent:** asking again while a run is in progress returns that run. The run's id is
  derived from its number, so a retried `begin` changes nothing.

### Trusted measurement only

Targets in load and chaos probes may use only what the platform measures. Content validation
enforces it: a target naming an app-reported metric fails `devgrill-content validate`.

What the verifier trusts:
- **k6's numbers**, measured client-side from the probe container: p99, p95, error rate, requests.
- **Postgres's core statistics**, read through the read-only role:
  - `db_scans_per_request` and `db_scans_per_s`: table scans across every user table, over the
    replay;
  - the session pins `search_path = pg_catalog, …` and names `pg_catalog` explicitly, so objects
    the app role creates can't stand in for the catalog.
- **Platform exporters:** e.g. `db_connections` from postgres_exporter.
- **Chaos recovery** (`recovery_s`), computed by `dg-recovery` from k6's per-request CSV, not from
  the app's metrics.
- **Probe scripts' own output:** invariants and hidden tests.

The app's metrics still drive the charts and mitigation detection during play. The standard
**honest-metrics** probe compares them with what k6 measured (`request_count_drift`,
`error_rate_drift`). Forged telemetry fails verify.

### The player is not a database superuser

ShopKart's database image (`content/base-apps/shopkart/db`):
- **`postgres`** is the superuser. Its password is random and thrown away at build time; the
  platform uses the container's local socket.
- **`shopkart`** (the app and the player) owns the app's tables, so faults and fixes can migrate
  and index them. It can't reset statistics, drop or replace the stats extension (now in a
  `monitor` schema owned by `postgres`), create schemas, write files or alter roles.
- **`verifier`** is read-only.

### Fail closed, and check that chaos happened

- A metric that can't be measured fails its target.
- Statistics that were reset or went backwards during a replay fail the probe.
- A cache flush must answer `OK`: `redis-cli` exits 0 even on an `ACL` refusal, so the answer is
  checked.
- A toxic must still be there at the end of the chaos window.

### Anti-cheat is standard

Every published playable scenario needs a `hidden_test` probe (schema validation).

ShopKart ships one as `content/base-apps/shopkart/verify/correctness.py` (referenced as
`base/correctness.py`). It checks, against the database:
- hot and cold product pages match the database;
- unknown products are 404s;
- search searches;
- orders are written at the right total;
- price changes show on hot and cold products within seconds.

It fails these fake fixes: answering 503, made-up or stale data, dropped writes, serving only
the sale products.

### Approaches and cheats are content, and the red team is code

- **`approaches/*.yaml`** have runnable steps (a patch, a command, or `rollback_to` a deploy), a
  declared outcome (`full`, `partial` with exactly which probes fail, or `fails`) and a `match`
  rule the debrief uses to recognise the player's approach.
- **`cheat: true` entries** are fake fixes and tampering attempts. They must fail verify, and
  they are never shown or seeded. A cheat's *command* may be refused by the sandbox (that is
  the point); a cheat's *patch* that doesn't deploy is broken content.
- **`devgrill-content test --approaches`** runs every approach and cheat in a fresh sandbox. CI
  runs it nightly and on content changes, one job per scenario.

### Scoring: an incident score that ratings use, and a total that adds the postmortem

`devgrill.domain.scoring`, property-tested. The components:
- **Mitigation time vs par:** 1 up to par, falling linearly to 0.25 at three times par, 0 if
  never mitigated.
  - Par is `par_minutes` (default: half of `est_minutes`).
  - Credit needs a verify run that held the SLO under replay and chaos. Mitigation is detected
    from the app's own metrics during play, so it counts once the verifier has measured the
    same recovery from outside.
- **Resolution:** the weighted share of probes the best verify run passed (partial credit).
- **Communication:** status updates posted: one earns 0.6, two earn 1. Phase 6 grades them.
- **Hints:** minus 0.1 per hint.

The **incident score** renormalises everything but the postmortem. Ratings use it, so a later
postmortem grade (phase 6) never moves a rating. The **total** adds the postmortem once it is
graded.

### Ratings: one Glicko-2 game per finished attempt, settled once

`devgrill.domain.ratings` and `devgrill.infra.settle`. After teardown, the lifecycle runs
`attempt.settle` (idempotent, one transaction). It:
- scores the attempt;
- recognises the approach;
- plays one game, player vs scenario, with the incident score as the result;
- updates both ratings, writes the rating history and the activity day, and refreshes the
  streak.

The rules:
- **Bounded:** every change is capped at ±120. The cap applies first, then guided mode halves
  gains, so a guided gain is exactly half the on-call one. Losses are never scaled.
- **Not rated:**
  - guests;
  - tutorials;
  - failures on our side;
  - leaving within 3 minutes without running verify ("wrong scenario").
- **Rated:** running out of time is a loss.

### The debrief and the postmortem

`GET /v1/attempts/{id}/debrief` returns:
- the score and the rating change;
- track mastery before and after;
- the best verify run with targets;
- the investigation replay, with markers from the scenario's `replay` rules (key clues, lost
  time) and every hint;
- the approaches, with shares and yours marked, only once the player has resolved the scenario;
- the next drills.

The postmortem is four markdown sections, saved as a draft and submitted once, with the timeline
from the trail added. It is ungraded until phase 6.

## Consequences

**Positive:**
- A broken fix can't pass by changing what verify reads: the red-team checklist runs on every
  nightly build (`docs/qc/phase-5-red-team.md`).
- Verify is fast enough to run often (1–2 minutes), and every run is visible probe by probe.
- Scores and ratings are recomputable from stored runs and events.

**Negative:**
- Approach recognition is rule-based until phase 6; an approach no rule describes is
  "unrecognised".
- The content tests now take about 15–25 minutes per scenario. CI runs them per scenario, in
  parallel.
- A toxic-based chaos probe could be dodged by an app that connects to the datastores directly,
  bypassing Toxiproxy. No shipped scenario uses one yet; splitting the sandbox network so only
  Toxiproxy reaches the datastores comes with the first one.

## Alternatives considered

- **One verify activity (phase 3's shape).** Rejected: no per-probe retries, and no progress
  outside the activity.
- **Verifying the app's metrics against a secret.** Rejected: the app is the player's code, so
  anything it reports is theirs to forge. Measuring from outside is simpler and stronger.
- **Rating only resolved attempts.** Rejected: abandoning to dodge a loss would become a
  strategy. Running out of time is a result.
