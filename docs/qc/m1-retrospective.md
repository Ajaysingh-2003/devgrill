# M1 retrospective: the vertical slice

Date: 2026-10-21 · Covers phases 0–5 (PLAN §15: "M1 at ~20 weeks").

## Where M1 stands

One scenario plays end to end locally, and two more are fully playable:
1. **Start:** a guest or a signed-in player starts from the briefing.
2. **Boot:** a real sandbox boots in about 20–40 s.
3. **Play:** the player investigates with the terminal, logs, charts, database and cache panels, the code editor and deploys.
4. **Mitigation:** it is detected from the system itself.
5. **Verify:** it attacks the fix from outside (1–2 minutes).
6. **Debrief:** it explains the result with a score, a rating change, the investigation replay and the known approaches.
7. **Postmortem:** the player writes and submits it.

The loop runs in a real browser against the real stack in CI nightly (the `workspace` job). Every scenario's reference fix, known approaches and cheats are tested in real sandboxes in CI nightly (`break-fix`, one job per scenario).

**Calendar:** the plan budgeted about 20 weeks of part-time work for M1. Phases 0–5 were built between 2026-10-12 and 2026-10-21 with an AI pair doing most of the typing. The owner's review, playtesting and sign-offs are what's left (see "Owed" below), and they are the real constraint from here.

## Keep

- **Content as tests.** A scenario is only real when `devgrill-content test` proves it:
  - it breaks as declared;
  - the reference fix passes;
  - each approach gives its declared outcome;
  - each cheat fails.

  This caught a broken cheat patch (a variable between a decorator and its function) that would otherwise have "passed" for the wrong reason.
- **Trusted measurement.** Verify trusts only what the platform measures. Moving the probe targets off the app's own metrics (phase 5) closed the biggest hole.
- **Temporal for anything with a lifetime.** Sandboxes, verify runs and settling are all workflows or activities with retries and guaranteed teardown. The time-skipping tests make the rules cheap to prove.
- **Demo sources for UI work.** The workspace, the debrief and the postmortem render from canned data at `/incident/demo/…`, so design, axe and keyboard tests run without Docker.
- **Gates with numbers.** Every phase has a QC report with measured results and its deviations written down.

## Cut or defer

- **The nine draft scenarios** stay `playable: false` until Phase 7. Each live scenario costs about a day: the faults, the probes, two or three approaches and two or three cheats, plus a calibration run.
- **Toxic-based chaos** waits for the split sandbox network (ADR 015, known limits). Cache flushes and restarts cover the current scenarios.
- **Firecracker, multiplayer and the scenario generator** remain post-launch (PLAN §17).
- **The verify artifact store** keeps a JSON per probe; k6 CSVs are deleted after analysis. Keep it lean until someone needs more.

## Risks seen at M1

- **Content throughput** is now the bottleneck, not the platform. Phase 7's 17 new scenarios at about a day each is 3–4 weeks of part-time work on its own.
- **CI time:** content tests take 15–25 minutes per scenario on a GitHub runner. At 20 scenarios that's about 20 parallel jobs nightly: fine for nightly, too slow for every push. Content PRs should run only the scenarios they touch.
- **Owner-only gates are piling up:**
  - the "Not LeetCode" sign-off (phase 1);
  - NVDA and 3 usability sessions (phase 4; `/review-animations` is done);
  - the M1 demo review (this phase).

  They are cheap individually and should be cleared before phase 6 adds AI behaviour that also needs human judgement.
- **One machine.** Everything runs on Docker Desktop on Windows. Track H (hosting) has to prove the same isolation on Linux with Sysbox; nothing in M1 depends on Docker Desktop specifics beyond the npipe transport.

## Re-estimate (part-time, about 15–20 hours a week)

| Phase | Plan | New estimate | Why |
|---|---|---|---|
| 6: AI layer | 3 weeks | 3–4 weeks | The golden set of 60 hand-graded postmortems is owner work and can't be generated |
| 7: Content, progression, onboarding | 5 weeks | 6–7 weeks | Content cost is now known: about a day per live scenario with its approaches, cheats and case file |
| 8: Hardening, local RC (M2) | 4 weeks | 3 weeks | Much of the hardening is done: isolation, limits, tamper-proof verify, the soak |
| 9: Growth, launch-ready (M3) | 4 weeks | 4 weeks | Unchanged |
| Track H | owner's call | unchanged | Trigger after M2 playtests |

M2 moves from week ~32 to about week 32–34 of part-time work from the start, mostly through content.

## Owed before phase 6

1. Review the M1 demo capture: `apps/web/test-results/video/` after `RECORD=1 node apps/web/e2e/live-flow.mjs`, or the CI artifact.
2. Clear the open owner gates listed under "Risks seen at M1".
3. Decide whether postmortem grading should be able to move a rating. ADR 015 says no: ratings use the incident score only.
