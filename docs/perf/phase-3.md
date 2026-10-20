# Phase 3 performance: sandboxes

Date: 2026-10-20.

**Machine:**
- Windows 11, Docker Desktop with engine 29.8.1 (cgroup v2).
- 12 CPUs and 8 GB for the Docker VM.
- Images were pre-built (`devgrill-content build`).

All numbers come from the scripts named below and can be re-run.

## Time to active (gate: < 45 s)

"Active" means the player can act:
1. the sandbox is up and healthy;
2. the faults due before T are applied (including their deploys);
3. the sale load is running.

| Measurement | Runs (s) | p50 | max |
|---|---|---|---|
| Driver only, `scripts/sandbox_gate.py timing -n 5` (ttl-zero), **seed baked into the Postgres image** | 26.8, 27.6, 26.2, 23.5, 24.3 | **26.2 s** | **27.6 s** |
| Same, before baking (Postgres initialised and seeded 370k rows on every boot) | 44.6, 41.7, 33.3, 33.7, 33.4 | 33.7 s | 44.6 s |
| Through the whole stack: `POST /v1/attempts` → Temporal → worker → `active` (`scripts/attempt_e2e.py happy`, workflow timestamps) | 34.0 | n/a | n/a |

**Where the time goes (baked):**

| Step | Time |
|---|---|
| Dependency waits (Postgres and Valkey healthy, then Toxiproxy, then the API) | about 10 s |
| The shell's git repo with history | about 2 s |
| The fault's config deploy (API restart and readiness) | about 8 s |
| Load start | under 1 s |

The full-stack run adds the worker's database writes and Temporal scheduling.

**Baking the seed:** `content/base-apps/shopkart/db/Dockerfile` (ADR 012) took Postgres from about 15 s of init on 1 CPU to about 2 s.

## Sandbox footprint

**Measured** (big-sale-meltdown, faulty, 40 VUs of sale traffic, 60 s window, `ComposeDriver.usage`):

| Resource | Use |
|---|---|
| Memory | **580 MiB** for all 9 containers |
| CPU | **about 2.6 cores**, including k6 in the probe container |

**Limits** (the ceiling one sandbox can take):

| Resource | Limit |
|---|---|
| CPU | 7.0 |
| Memory | 3.1 GiB |
| pids | 256 per container (512 for the shell) |

**Consequence for hosting (ADR 013, PLAN §12.4):** CPU, not memory, limits density.
- A 64 GB box fits about 100 sandboxes by RAM, but only about 6 at full sale load on 16 cores.
- Players are rarely all at peak, and play-time load can be lower than verify-time load.
- Revisit both before Track H.

## Lifecycle reliability (gate: 50 create → destroy, 0 leaks)

**`scripts/sandbox_gate.py leaks -n 50`:**
- 50 cycles in 29.9 minutes, 0 boot failures.
- Leftover containers 0 and networks 0, before and after.
- Dangling volumes on the host: 12 → 13.
  - The extra volume was traced to a manual `docker run` of the baked Postgres image, made during the run and removed with `docker rm -f`. It was an empty, postgres-owned `/var/lib/postgresql`.
  - Sandbox containers mount tmpfs over every volume their images declare.
  - The volume was removed.

**`leaks -n 10` again, with the baked image:** 0 containers, 0 networks, dangling volumes 12 → 12.

## Break, fix, verify (gate: symptoms within 60 s; the reference fix passes every probe)

**`devgrill-content test`** (reports in `content/.reports/`):

| Scenario | Boot | SLO breached after | Symptom | Mitigated after the fix | Probes |
|---|---|---|---|---|---|
| ttl-zero (SEV4) | 16.5 s | 7.5 s (database reads 3× normal) | hit rate 0 at 7.5 s | at once (healthy for 30 s) | sale-replay p99 121 ms, 0 errors; db-offload 30.5 reads/s (< 75); budget ✓ |
| pool-party (SEV3) | 19.3 s | 5.7 s (p99 2.3 s) | p99 > 500 ms at 5.7 s | at once | steady-traffic p99 150 ms, 0 errors; connection-headroom 31 (< 70); budget ✓ |
| big-sale-meltdown (SEV2) | 15.4 s | 7.9 s (p99 1.7 s) | hit rate 0 at 7.9 s | at once | sale-replay p99 162 ms, 0 errors; hit rate 0.85; cold-cache recovery 2.8 s; price freshness 0.06 s; budget ✓ |

## Isolation (`scripts/sandbox_gate.py isolation`)

| Check | Result |
|---|---|
| `curl https://example.com` from the shell | fails (no DNS, no route) |
| `curl http://1.1.1.1` | fails |
| The host (`host.docker.internal:5432`) | unreachable |
| The platform's own containers (Postgres, Valkey, Temporal...) by IP | unreachable |
| Fork bomb in the shell | fills the shell's pids limit and stops there; the API keeps serving; a restart recovers the shell |
| Allocating 2 GiB in the shell (512 MiB limit) | OOM-killed (exit 137); the API keeps serving |
