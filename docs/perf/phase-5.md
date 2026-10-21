# Phase 5 performance: verify

Date: 2026-10-21. Same machine as `docs/perf/phase-3.md`: Windows 11 and Docker Desktop, with 12 CPUs and 8 GB for the Docker VM.

## Verify duration (gate: < 4 minutes per scenario)

Measured by `devgrill-content test <slug> --approaches`, from the first probe to the verdict, on fixed and unfixed systems.

| Scenario | Probes (groups) | Reference fix | All runs (approaches and cheats) |
|---|---|---|---|
| ttl-zero | 5 (3) | **50.8 s** | 54.6 s for the static-hot cheat |
| pool-party | 5 (3) | **49.6 s** | 56.4 s for `bigger-pool` |
| big-sale-meltdown | 7 (5) | **91.6 s** | 89.6–116.5 s; the slowest is `read-plain-key`, whose price checks wait out their deadlines |

**Slowest run:** 116.5 s, against a 240 s budget.

**Where the time goes** (big-sale-meltdown):

| Part | Time |
|---|---|
| One shared replay for the three load probes | 45 s, plus scrapes and statistics |
| The cold-cache chaos window | 40 s |
| Correctness and freshness scripts | a few seconds each when the system is right; up to their deadlines when it isn't |
| The budget check | under a second |

Sharing the replay saved about 90 s per big-sale-meltdown run: three load probes once had three replays.

**In the browser** (the full loop, `apps/web/e2e/live-flow.mjs`, ttl-zero): **55 s** from the Verify click to "Verify passed", including the workflow's start and the progress events.

## The full loop (gate: E2E to the debrief)

| Step (ttl-zero, guest) | Elapsed |
|---|---|
| Start → active | 30 s (20–30 s across runs) |
| Terminal echo p50 / p95 | 8 / 24 ms |
| Roll back → mitigation detected | 40 s |
| Fix the config in the editor → deploy | 12 s |
| Verify → passed | 55 s |
| Debrief settled and shown | 14 s |
| Postmortem drafted and submitted | 11 s |
| **Whole loop** | **3 min 33 s** |

## Content tests

A scenario's full suite (the reference fix, then each approach and cheat in a fresh sandbox) runs 3–4 minutes per sandbox locally: boot 16–25 s, the break up to 60 s, the fix plus 20 s to settle, then verify.

| Scenario | Sandboxes | Local time |
|---|---|---|
| ttl-zero | 7 | about 25 minutes |
| big-sale-meltdown | 7 | about 25 minutes |
| pool-party | 5 | about 17 minutes |

CI runs the scenarios in parallel, one job each, with a 60-minute limit per job.

## Measurements that separate fixed from broken

| Measurement | Fixed | Broken (or cheating) | Target |
|---|---|---|---|
| `db_scans_per_request` (ttl-zero) | 0.55 | 1.96 (forged metrics), 1.94 (statistics reset refused) | under 1.0 |
| `db_scans_per_request` (big-sale-meltdown) | 0.52 | 1.99 (forged metrics) | under 1.0 |
| `request_count_drift` | 0.05–0.24% | not measured when the app's metrics are missing | under 10% |
| `recovery_s` after a cold cache (big-sale-meltdown, from k6's per-request results) | 6 s | not measured (no successful requests) | under 30 s |
