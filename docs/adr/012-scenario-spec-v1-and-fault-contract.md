# 012. Scenario spec v1, the fault contract, and the local sandbox (phase 3)

Date: 2026-10-20 · Status: accepted

## Context

Phase 3 turns scenarios from library metadata into incidents that really happen. A
scenario has to:
- boot a real system;
- break it in a way the player can find;
- prove it broke as promised;
- prove its reference fix works.

All of that has to come from files in `content/`, validated in CI, without anything
Docker-specific leaking into the content (ADR 007). This ADR records:
- the file formats (spec v1);
- the fault contract;
- how the local driver isolates, operates and measures a sandbox.

## Decisions

### Content formats (spec v1)

Pydantic models are the source of truth, and `devgrill-content schema` exports them as
JSON Schema:
- `devgrill.domain.spec`: scenario, fault, solution and approach;
- `devgrill.sandbox.baseapp`: base app.

Every file names its format: `schema: devgrill/<kind>@1`.

1. **Base app** (`content/base-apps/<slug>/base-app.yaml`). This is the system: services,
   their dependencies, healthchecks, limits, and the files copied in before start.
   - **Roles are explicit flags**, not naming conventions:
     - `shell`: the player's terminal; exactly one service has it;
     - `source`: patchable;
     - `sql`: runs `.sql` faults;
     - `toxiproxy`;
     - `cache`;
     - `port`/`metrics`: the load target and scrape path.
   - **Metrics are declared structurally**, not as PromQL. Each one names a job, a metric and
     label regexes, and is one of four types: `gauge`, `rate`, `ratio` or `quantile`. One
     small evaluator (`devgrill.sandbox.metrics`) computes them from two scrapes. That is all
     the SLOs, symptom checks and probes need, and there is no query engine to run.
2. **Fault module** (`content/faults/<category>/<name>/fault.yaml`). A fault declares:
   - **One mechanism per step**:
     - `patch`: a unified diff with paths relative to the service root, applied with
       `git apply -p0`;
     - `env`: overrides;
     - `toxic`: a Toxiproxy toxic;
     - `script`: `.sql` via psql, `.py` or `.sh`; it may be `detach`ed for faults that must
       keep running, such as a transaction holding a lock.
   - An optional second step, `also`.
   - An optional `revert`. Patch, env and toxic revert automatically; scripts need an
     explicit revert.
   - **Typed params** with defaults, substituted as `{{name}}`. Unknown params and unknown
     placeholders are errors.
   - **The symptom contract**: `metric op value within_s`.
3. **Scenario** (`scenario.yaml`):
   - **`playable: false`** marks library placeholders. A published playable scenario must
     have page, faults, load, slo, probes and hints.
   - **`access: free | pro`**: see ADR 013.
   - **Fault timing is relative to T, the moment the load starts.**
     - Negative offsets (`T-2m`) are narrative only: they are applied before the load, so
       the player arrives at an incident already in progress. They set commit dates, but
       nobody waits for them.
     - Positive offsets fire on workflow timers.
   - **`slo`** is latency and/or error rate, plus optional `thresholds` on any base-app
     metric. Capacity incidents (ttl-zero) are paged on database load, not user latency.
   - **`deploy_history`** becomes real git commits in the shell's repo. Commit SHAs are real,
     so the spec no longer carries them. Deploys made by faults must be the newest entries,
     because faults are committed last.
   - **Beats** fire `at` a time or `when` an event happens. The key is not `on`, because
     YAML 1.1 reads `on` as `true`.
4. **Solution** (`solution/solution.yaml`): patches (committed and deployed) or commands.
   `devgrill-content test` applies it.

### The fault contract

Every playable scenario must pass `devgrill-content test`. It follows the same order as a real
attempt:

1. boot;
2. apply the faults due at or before T;
3. start the load;
4. apply the later faults on time;
5. **BREAKS**: every fault's symptom appears and the SLO is violated within 60 s;
6. apply the solution;
7. **MITIGATED**: the SLO holds for `for_s` within 150 s;
8. stop the play load;
9. **PROBES**: every probe passes.

`devgrill-content validate` runs without Docker and checks:
- every format;
- every cross-reference (the services, params and metrics that faults and probes use);
- that **every patch still applies**: faults against the pristine base app, and each
  scenario's solution on top of its faults.

That last check means a base-app edit can't silently break content.

### Config is code

Tunables for patchable services live in a committed file (`config/app.env`). Process env
keeps only what the platform owns, such as `REDIS_URL`.
- An `env` fault on such a service edits the file, commits it with the scenario's deploy
  message, and deploys.
- A bad config therefore shows up in `git log` and `git show`, and can be reverted and
  redeployed like any change.
- `env` faults on other services recreate the container with the new environment.

### The local driver (ComposeDriver)

It talks to the **Docker Engine API (aiodocker), not the compose CLI**. It needs per-step
control:
- dependency waits;
- files before start;
- recreating one service;
- idempotent create and destroy from Temporal activities.

**Isolation:**
- **One sandbox is one `internal: true` network.** There is no egress and no route to the host
  or the platform's containers.
- **Nothing is published on the host.** The platform reaches in only through the Docker API.
- **Every container has limits:**
  - CPU (`NanoCpus`);
  - memory with no swap, so a leak ends in an OOM kill, as in production;
  - pids (256, and 512 for the shell);
  - `NET_RAW` dropped;
  - `no-new-privileges`;
  - bounded json logs.
  - Services restart `on-failure`, like under any orchestrator.
- **Volumes an image declares are mounted as tmpfs**, so a sandbox can never leave a volume
  behind.
- **Everything carries `devgrill.*` labels.** `destroy` and the sweeper
  (`devgrill-content sandboxes --sweep`) find sandboxes by label.

**The probe container:**
- It is platform-owned and sits on the sandbox network.
- It has curl, psql, redis-cli and k6. The player never gets a shell in it.
- Scrapes, the play load, Toxiproxy admin calls, chaos steps and invariant checks all run
  there, out of reach of root in the player's shell (PLAN §12.3).

**Patchable services:**
- Their build folder is copied into the shell as a git repo (`/workspace/<service>`), with
  the scenario's history.
- Deploying copies the working tree (or a commit, for rollbacks) into the service and
  restarts it. Dependencies are baked into the image, so there is no image rebuild per
  deploy.

**Datastores are pre-baked:**
- ShopKart's Postgres image is built with its seed already loaded: the entrypoint's
  initialisation runs at build time, and PGDATA sits outside the image's VOLUME.
- A sandbox's database starts in about 2 s instead of seeding 370k rows on every boot.

**Images are content-addressed:**
- Every built image carries a `devgrill.content-hash` label (the hash of its folder).
- Boot rebuilds only what changed.
- Builds shell out to `docker build` (BuildKit), because the Engine API's builder is the
  legacy one.

**The base app is fit for measurement:**
- The API runs Prometheus in multiprocess mode, so a scrape sees all four uvicorn workers.
- It labels requests by route template, not raw path.
- A product read includes a rating summary over reviews. That makes it expensive enough
  that caching matters, which is how sale-scale incidents become real.

## Consequences

**Positive:**
- Content is reviewable YAML and diffs.
- CI proves every scenario can break and can be fixed, without Docker for the static checks.
- The isolation gate is measured, not assumed:
  - egress is blocked;
  - the platform is unreachable;
  - fork bombs and memory hogs stay inside their own container.

**Negative:**
- The structured metric definitions are less expressive than PromQL. New metric types must
  be added to the evaluator.
- Docker Desktop is slower than Linux. Time to active is measured on this machine
  (`docs/perf/phase-3.md`).

**Follow-ups:**
- Phase 4: the gateway, the `devgrill` CLI's control endpoint, and PTY.
- Phase 5: hidden tests, scoring and approaches.
- Track H: the Sysbox driver behind the same protocol.

## Alternatives considered

- **The compose CLI as the driver.** Rejected: the CLI is a subprocess (and a `.cmd` shim
  risk on this machine), state is opaque between steps, and recreating one service with new
  env is awkward.
- **PromQL strings and a real Prometheus per sandbox.** Rejected: an extra service per
  sandbox, plus a query engine just to compute four kinds of number.
- **Publishing sandbox ports on localhost for scraping.** Rejected: it breaks the
  "no route in" rule and collides across sandboxes. The probe container does it from the
  inside instead.
