# Phase 7 QC report: content, progression and onboarding

Date: 2026-10-27 · Result: **IN PROGRESS** (wave 7A done) · Decision: ADR 017.

Phase 7 runs in waves, each tested and committed on its own:

| Wave | Scope | Status |
| --- | --- | --- |
| 7A | Daily rotation, pro mode, public profile opt-in, primers, library filters, share card | Done |
| 7B | `/try` guest tutorial with progressive unlocks and tips | Next |
| 7C | Quick Fire cards and onboarding calibration | |
| 7D | Streak freezes and on-call leave, email digests (Mailpit) | |
| 7E | Admin console: RBAC, audit log, review queue, publish and retire | |
| 7F | Content sprint toward 20 drills, the Ledger app | |
| 7G | Case files | |

## Wave 7A: what was built

- **Daily rotation (ADR 017):**
  - only playable scenarios; `daily: false` opts one out;
  - shuffled cycles with no consecutive repeats (property-tested over 200 days for pools of
    2, 3 and 7);
  - the Temporal schedule `challenge-rollover` at 00:01 IST.
- **Pro mode:** hides the streak in the top bar and on your own profile, and skips the results
  page celebration. Ratings stay.
- **Public profile opt-in:**
  - new profiles are private (migration 0005, round-tripped and `alembic check` clean);
  - the owner can still see their own profile;
  - a switch in Settings.
- **Primers:** 27 four-minute reads in `content/primers/`, one per topic, validated by the content
  loader. They open from a "Read the primer" disclosure on each track page.
- **Library filters:**
  - "All drills" on `/drills`, with search plus severity, progress (signed in) and plan filters;
  - instant filtering on the client, with a polite live count and an empty state;
  - playable drills listed first, then "Coming soon" ones;
  - drill cards now carry `access` and `playable`.
- **Share card (ADR 017):**
  - `GET /v1/share/{attempt_id}` and the public page `/share/[attemptId]`, with an Open Graph
    image;
  - "Share your result" on the results page (system share sheet, or copy the link);
  - spoiler-free and anonymous by test.
- **Security:** Next 16.4.3 and overrides for zod, body-parser and undici (the critical advisories
  that failed CI hygiene).

## Checks run (wave 7A)

- **Python:** 337 passed, including the query-plan budget with the new join.
- **Web:**
  - e2e: 53 passed, 1 skipped, including a new filter test;
  - UI component tests pass;
  - lint, types, Prettier, copy, colour and line-ending checks are clean.
- **Content:** `devgrill-content validate`: 12 scenarios, 0 problems. The seed loads 27 primers.
- **By hand:** `/drills` at 1280 and 390 px, the share page, and the share image.

## Gate checklist (docs/PLAN.md, Phase 7), so far

- [ ] All 20 scenarios pass `devgrill-content test` nightly (7F).
- [ ] Each scenario playtested by someone other than its author (7F).
- [ ] Time-to-first-win on `/try` (7B).
- [ ] Daily rollover across time zones; share card with no spoilers; pre-warm pool.
  - Done in 7A: the rollover and the share card.
  - Owed: the pre-warm pool, and the card in dark mode (OG images are light only).
- [ ] Streak logic property-tested; notification caps (7D).
- [ ] Admin RBAC and audit log (7E).
- [ ] Design QC and the ethical-gamification checklist.

## Fixed along the way

- **Settings switches:** the Pro mode and Public profile switches were named by their state text
  ("On", "Only you"). They are now labelled by their section headings.
- **Worker imports:** the rollover workflow imported infrastructure inside the workflow sandbox.
  Those imports now pass through, and the existing worker test caught it.

## Owed

- **Share image weight:** the Open Graph image renders in the default OG font, regular weight
  only. Vendoring the Arcade font (Bricolage Grotesque) for share cards is left for the Phase 9
  result cards.
