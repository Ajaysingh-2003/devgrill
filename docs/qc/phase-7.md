# Phase 7 QC report: content, progression and onboarding

Date: 2026-10-27 · Result: **IN PROGRESS** (waves 7A to 7C done) · Decision: ADR 017.

Phase 7 runs in waves, each tested and committed on its own:

| Wave | Scope | Status |
| --- | --- | --- |
| 7A | Daily rotation, pro mode, public profile opt-in, primers, library filters, share card | Done |
| 7B | `/try` guest tutorial with progressive unlocks and tips | Done |
| 7C | Quick Fire cards and onboarding calibration | Done |
| 7D | Streak freezes and on-call leave, email digests (Mailpit) | Next |
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

## Wave 7B: what was built

- **`/try`:** a no-account page that starts ttl-zero in tutorial mode, signing in a guest when
  nobody is signed in. The landing page's "Try a 5-minute drill" now opens it.
- **Tools unlock step by step** (tutorial mode only):
  - Overview and Logs first;
  - Cache once Logs has been opened;
  - Code and Deploys once Cache has been opened;
  - the terminal stays locked ("unlocks in a later tutorial").

  Locking is guidance: the API accepts any action the scenario allows.
- **The incident lead's tips:** one per step ("Start with the page", "Follow a request", "Ask
  what changed", "Prove it"), dismissible and shown once.
  - **Progress:** advances on what the player does.
  - **Persistence:** saved per attempt in localStorage, with memory as the fallback.
  - **Announcement:** polite, with no motion.
- **Clock:** hidden by default in the tutorial, as in guided mode.
- **Results page for guests:** "Keep this win" leads to GitHub sign-in, and the run is claimed
  on sign-in.
- **Deviation from PLAN §8.3:** the plan's tutorial was "Terminal and Logs, an OOM, a one-command
  fix". The tutorial drill is ttl-zero, whose fix is a config change and a deploy, so the
  tutorial unlocks Code and Deploys instead of the terminal.

## Checks run (wave 7B)

- **e2e:** 59 passed, 1 skipped.
  - New: tools unlock step by step, tips advance and stay dismissed after a reload (the demo
    workspace has a tutorial variant at `/incident/demo?tutorial=1`).
  - `/try` and the tutorial workspace are added to the WCAG sweep in both themes.
- **By hand:** `/try` and the tutorial workspace at 1280 px.

## Wave 7C: what was built

- **48 Quick Fire cards:** eight per published track, in `content/quickfire/`, validated by the
  content loader (strict schema, unique slugs, known tracks) and seeded by slug (migration 0006).
- **Quick Fire API:**
  - `GET /v1/quickfire/deck`: random cards, without answers;
  - `POST /v1/quickfire/cards/{id}/answer`: right or wrong, the answer and why.
- **`/quickfire`:** now real.
  - Three minutes and three strikes.
  - Keys 1 to 4 answer and Enter moves on.
  - Each answer is revealed with icon, label and colour, plus the explanation.
  - An end card offers "Play again".
- **Onboarding (`/onboarding`):**
  - experience and role;
  - then an optional six-card calibration, one card per track;
  - "Skip for now" works at the first step.

  Sign-in offers it once to new accounts. Starting ratings follow ADR 017: hidden until a
  rated game, and never overwriting a track already rated.

## Checks run (wave 7C)

- **Python:** new API tests (the deck hides answers, the answer check, onboarding seeds once
  and needs an account), a calibration domain test and content loader tests.
- **e2e:** 61 passed, 1 skipped.
  - New: the onboarding flow end to end, with its database rows checked.
  - New: a Quick Fire run by keyboard.
  - The sign-in helper skips onboarding for other tests.
- **Migration 0006:** round-tripped, and `alembic check` is clean.
- **By hand:** Quick Fire at 390 px.

## Gate checklist (docs/PLAN.md, Phase 7), so far

- [ ] All 20 scenarios pass `devgrill-content test` nightly (7F).
- [ ] Each scenario playtested by someone other than its author (7F).
- [ ] Time-to-first-win on `/try`: the flow is built (7B). It still needs 5 new users, median under 5 minutes.
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
- **Ctrl+Enter deploy (found by CI's real-sandbox flow on the 7A push):** the dependency
  refresh deduplicated `@codemirror/view`.
  - **Cause:** `codemirror`'s `basicSetup` had been bound to its own copy, so its keymaps never
    fired. Once live, its Mod-Enter ("insert blank line") shadowed the editor's deploy shortcut.
  - **Fix:** the editor's keymap is now `Prec.highest`.
  - **Test:** a demo e2e test checks Ctrl+Enter on every run. It fails without the fix.

## Owed

- **Share image weight:** the Open Graph image renders in the default OG font, regular weight
  only. Vendoring the Arcade font (Bricolage Grotesque) for share cards is left for the Phase 9
  result cards.
