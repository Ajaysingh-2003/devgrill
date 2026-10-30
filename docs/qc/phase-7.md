# Phase 7 QC report: content, progression and onboarding

Date: 2026-10-27 · Result: **IN PROGRESS** (waves 7A to 7E done) · Decision: ADR 017.

Phase 7 runs in waves, each tested and committed on its own:

| Wave | Scope | Status |
| --- | --- | --- |
| 7A | Daily rotation, pro mode, public profile opt-in, primers, library filters, share card | Done |
| 7B | `/try` guest tutorial with progressive unlocks and tips | Done |
| 7C | Quick Fire cards and onboarding calibration | Done |
| 7D | Streak freezes and on-call leave, email digests (Mailpit) | Done |
| 7E | Admin console: RBAC, audit log, review queue, publish and retire | Done |
| 7F | Content sprint toward 20 drills, the Ledger app | In progress (6 of 8 drills built) |
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

## Wave 7D: what was built

- **Streaks (ADR 017):**
  - freezes are earned (1 per 7 days in a row, or 4 weeks in weekly mode; 2 at most) and spent
    automatically;
  - on-call leave days are neutral;
  - any Quick Fire answer counts as the day's activity;
  - everything is still derived from activity.
- **Settings:**
  - "On-call leave": book a date range up to 90 days ahead, or cancel it.
  - "Daily email": opt-in, with a send time. GitHub must share an email.
- **The profile's activity grid:** shows leave as dashed cells, with the count in its text.
- **The daily email:**
  - today's drill and your streak, in plain words with no guilt;
  - sent by an hourly Temporal sweep;
  - at most once per local day (enforced by the database), never in quiet hours (22:00 to
    08:00);
  - a one-tap pause page, plus RFC 8058 one-click unsubscribe.

  Checked by hand in Mailpit (rendering and headers).
- **Migration 0007:** `leave_days`, `notifications_sent` and `profiles.email`. Round-tripped,
  and `alembic check` is clean.

## Checks run (wave 7D)

- **Python:** 362 tests pass.
  - New streak and digest property tests: DST in four zones, freezes, leave, quiet hours, at
    most one email per local day.
  - New API tests: leave range rules, Quick Fire activity, pause tokens, one-tap pause.
  - A digest sweep integration test: once in its hour, never in quiet hours, opt-outs and
    missing emails skipped.
- **Contract (Schemathesis):** passes. Business-rule refusals are 400.
- **e2e:** 65 of 65 passed across two runs, 1 skipped.
  - New: booking and cancelling leave; turning on the daily email; a forged pause link.
  - `/emails/pause` is added to the WCAG sweep.
  - Two signed-in accessibility tests failed on the first run with a Postgres connection
    timeout under parallel load. They passed on rerun.

## Wave 7E: what was built

- **Roles and lifecycle (ADR 017):**
  - authors submit drafts;
  - reviewers send back (with a reason), publish, retire and restore;
  - admins do everything, plus users, roles, AI spend and the audit log.

  The API enforces this per action.
- **Audit log:** every lifecycle step, role change and fix review is written in the same
  transaction. Admins can page back through it at `/admin/audit`.
- **Console sections:** Scenarios (status, report, actions), Analytics (with flags), AI and
  fixes, Users (lookup and roles) and Audit log. The navigation shows only the sections the
  role opens.
- **Seed:** it no longer overwrites a scenario's status after the first time, and attaches
  `devgrill-content test` reports to the current version.
- **Not built:**
  - **Playtest in author mode** (a sandbox with the solution visible and faults toggleable)
    needs sandbox work.
  - **Validation from the console:** reports come from `devgrill-content test` in CI and
    locally, and are attached at seed, but the console can't start a run itself yet.

## Checks run (wave 7E)

- **Python API tests:**
  - the role matrix in the policy, and through the API (authors can't publish, reviewers
    can't submit, only admins see the audit log and users);
  - a full lifecycle walk with its audit entries;
  - analytics flags from 12 runs;
  - user lookup with literal wildcards, and the guard on an admin's own role;
  - a re-seed keeping the console's status.
- **The authorization test:** it lists every `/v1/admin` route, including the new ones.
- **Contract (Schemathesis):** it found two things, both fixed.
  - Lifecycle actions moved to `/actions/{action}`, so they no longer shadow `/report`.
  - `PATCH /v1/me` returned a 500 for a display name with a NUL; display names now reject control characters, and a test covers it.
- **e2e:** 67 passed, 1 skipped.
  - New: retire and restore through the UI, then seen in the audit log.
  - A plain account sees no console sections.
  - Every console page is in the WCAG sweep.

## Wave 7F: drills, one at a time

The owner chose four drills first, each tested in real sandboxes and committed on its own.

- **The plan:**
  1. The 3 a.m. table lock.
  2. Restarts every six hours.
  3. Orders stuck in the queue (new).
  4. The index that wasn't (new, replacing "Order history crawls": it needs no traffic-mix
     change and teaches a classic real incident).
- **Deferred:** "Evicted at the worst time" and "One celebrity, one key" need base-app work
  first (user sessions, Redis shards).
- **Second batch (four more, same process):** the owner asked for four rather than all 13. All
  four run on ShopKart, in tracks that had no playable drill:
  5. Bestsellers are down (deploys/bad-config).
  6. Search pins the CPU (memory/runaway-regex).
  7. Stale prices (caching/invalidation): the library placeholder, made playable.
  8. A feature flag on for everyone (deploys/feature-flags).
- **Later:** the Ledger app and the drills that need it (concurrency, idempotency), the
  remaining placeholders, and case files (7G).

### Drill 1: The 3 a.m. table lock (databases/migrations, SEV2)

**The incident:** a migration (`application_name = 'migrator'`) runs
`ALTER TABLE orders ADD COLUMN ...` in a transaction and hangs before committing.
- In `pg_stat_activity` it shows as on-call sees it for real: idle in transaction, holding an
  ACCESS EXCLUSIVE lock.
- Checkouts wait on the lock while holding pooled connections. The pools drain, and product
  pages fail with 503s too, while Postgres sits idle.

**Lessons:**
- **Mitigate:** find the blocker (`pg_blocking_pids`) and end it.
- **Fix properly:** bound lock waits in the API (`DB_LOCK_TIMEOUT_MS`, new and off by default),
  so the next stuck lock costs checkout a few fast failures, not the site.
- **Traps:** a rollback doesn't release a database lock; a restart drops every connection to
  end one session.

**Platform pieces it needed:**
- **A `hold_sql` chaos step:** SQL run as the app's database user and held for the chaos
  window, then ended by its `application_name`.
- **k6 measures product pages on their own** (`product_p99_ms`, `product_error_rate`). The
  API's own latency metric is editable, so verify can't trust it.
- **An open-model replay** (`verify/open-traffic.js`, constant arrival rate). With a fixed set
  of virtual users, every user stuck on a locked checkout stops sending anything, and the
  outage hid itself. This was caught by the approach run, where "end the session only" first
  passed the guard probe.
- **ShopKart changes:**
  - the API honours `DB_LOCK_TIMEOUT_MS` (0 means wait forever) and answers a lock timeout
    with the usual 503 "database busy";
  - the terminal has `PG*` set, so `psql` just works as the app user.
- **Content CI discovers playable drills** (`devgrill-content list --playable --json`) instead
  of a hard-coded matrix.
- **Groundwork for drill 2:**
  - per-service memory from the driver, read by Docker from outside the container;
  - `app_memory_growth_mb` measured during replays;
  - a per-scenario `charts:` list for the Overview.

**Checks:**
- **`devgrill-content test --approaches` in Docker:** the reference fix and all five
  approaches gave their declared outcomes.
  - The reference fix: the break began within 7 s, it stayed broken when left alone, and it
    mitigated within a second of the fix. All four probes pass; during a new lock, product
    pages held 13 ms p99 with no errors.
  - Ending the session only: partial (`lock-guard` fails, with 16 s p99 and 4.7% errors).
  - Bounding lock waits only: fails (checkout stays down at 5%).
  - Rolling back: fails.
  - The checkout-refusing cheat: fails.
- **Played by hand** with `devgrill-content up`:
  - the blocker is visible in `pg_stat_activity` as `migrator`, idle in transaction with its
    ALTER TABLE;
  - one `pg_terminate_backend` brought uncached product pages back from 5 s 503s to 13 ms.

### Drill 2: Restarts every six hours (memory/leaks, SEV3)

**The incident:** last week's "memoise product lookups" deploy added a per-process dict, keyed
by product and the current second, that is never emptied. Memory grows with traffic until the
kernel kills the worker.
- At normal traffic that took six hours. At sale traffic it's about every 100 seconds: a
  readable sawtooth, measured at 2.5 MB/s with a kill every 100 s.
- **Mitigate and fix in one step:** roll back, remove the memo, or bound it.
- **Traps:** a bigger memory limit or timed restarts (both in the beats) only hide it.

**Design notes from measuring it:**
- **Paged on memory growth, not errors.** A killed worker takes its in-flight requests with
  it, unseen by the app's own error metrics.
  - The API now counts new per-worker memory highs (`app_memory_growth_bytes_total`). It's
    flat once warm and climbs for as long as something leaks.
  - The SLO pages on growth above 0.5 MB/s. A plain memory threshold failed: the sawtooth dips
    under any line for half of each cycle.
- **The API's memory chart** reports private memory (resident minus shared). A plain RSS sum
  counted pages the forked workers share once per worker: 578 MB against Docker's 390 MB.
  Workers also clear the gauges of OOM-killed workers at startup.
- **The leak was slowed tenfold,** from a kill every 10 to 20 s to one about every 100 s. It
  was also rewritten as a believable change (a memo with a view histogram for a "trending"
  widget). The old code's comment said "never evicted", which gave the answer away, and it
  returned the padding inside the product JSON.
- **Verify trusts Docker's view:** `memory-flat` sums the rises in the API container's memory
  during the replay, so a crash part way doesn't hide a leak. Healthy runs measured 3 to 7 MB
  against a 32 MB limit.

**Checks:**
- **`devgrill-content test --approaches` in Docker:** the reference fix and all four
  approaches gave their declared outcomes.
  - Roll back, remove the memo and cap the memo: all full.
  - The cheat that silences the growth metric: caught. The Overview would look flat, but
    Docker measured 96 MB of growth.
  - **CI found a problem I fixed:** "cap the memo" at 256 entries grew 46 MB on GitHub's faster
    runner, because the memo filled, cleared and refilled within the replay. It's bounded but
    churns about 40 MB, so the cap is now 64 entries (about 10 MB).
- **By hand with `devgrill-content up`:** the sawtooth seen from Docker and from the gauge,
  with worker deaths in the API's logs.

### Drill 3: The index that wasn't (databases/indexes, SEV2)

**The incident:** a migration drops `reviews_product_id_idx`, then builds its covering
replacement with `CREATE INDEX CONCURRENTLY`. The build has to wait for a nightly report's
older snapshot. The migration runner's watchdog cancels the step and logs only a warning, and
Postgres leaves the new index INVALID.
- `\d reviews` lists the index (with `INVALID` at the end), so "the index is there". The
  planner can't use it, though: EXPLAIN shows a parallel sequential scan.
- Every uncached product page scans 300,000 reviews, and Postgres saturates.

**Fixes:** `REINDEX INDEX CONCURRENTLY`, or recreate the old index. A plain REINDEX also works
but locks writes. A longer cache and a bigger database only hide the problem.

**Getting the fault right took three tries, each found by running it:**
1. **A 30 ms statement timeout was racy.** It sometimes cancelled the build before the index
   existed, so there was no index at all.
2. **Postgres applies neither `statement_timeout` nor `lock_timeout`** to a concurrent build's
   wait for older snapshots. The build simply waited 20 s and finished VALID.
3. **The deterministic version** is a long report holding a snapshot, plus a watchdog cancelling
   the waiting build, as real runners do. It gave INVALID in three of three fresh sandboxes.
   The report reads `orders`, because a lock on `reviews` would block the DROP instead.

**Tuning:** at 30 virtual users the break recovered by itself after 48 s, with Postgres just
under saturation, so the drill uses 45. The healthy p99 then sits at 250 ms against the 500 ms
SLO.

**Paging on the cause:** on CI's faster runners, the latency SLO still recovered by itself after
65 s. As the cache warmed, uncached reads thinned out and p99 dipped under target, while Postgres
kept scanning the table. The drill now also pages on `reviews_seq_rows`: rows per second read by
scanning `reviews`, measured by the Postgres exporter, with a target of under 100,000. Healthy
traffic reads none. The Overview charts it next to p99 (scenario `charts`).

**Platform pieces:**
- **`db_seq_rows_per_request`:** rows read by sequential scans, from Postgres's own statistics
  through the read-only role. Healthy reads 0 rows per request; the unusable index reads
  48,000. Plain scan counts couldn't tell them apart, because search already scans `products`.
- **ShopKart's correctness check now verifies rating summaries** against the reviews, so a fix
  that stops computing ratings fails. That makes 19 checks.

**Checks:** in Docker, the reference fix and all five approaches gave their declared outcomes:
- `REINDEX CONCURRENTLY`, recreating the old index and a plain REINDEX: all full;
- a longer cache: fails (48,000 rows per request, 1.6 s p99);
- the cheat that skips ratings: fails on correctness.

By hand with `devgrill-content up`: `\d reviews` shows `INVALID`, and EXPLAIN shows the
parallel sequential scan.

### Drill 4: Orders stuck in the queue (queues/poison-messages, SEV2)

**The incident:** after a payment blip dead-lettered some orders, a worker deploy set
`MAX_ATTEMPTS=0` ("never drop an order"). Then a partner's test message, with quantity 0, reached
the front of `orders:pending`.
- `charge()` rejects that message every time, and the worker retries a failed order at the head
  of the queue, so it retries this one forever.
- Every real order waits behind it, while checkout keeps answering 201.
- Users see no errors, so the page fires on queue depth (under 50 for 30 s), not latency.

**Fixes:** bound the retries again (`MAX_ATTEMPTS=3` in `config/worker.env`), roll the worker
back, or dead-letter invalid orders at once. Removing the bad message by hand is partial: the
next one stops the line again. Clearing the queue is a cheat: it loses every real order behind
the bad one.

**Base-app work (ShopKart):**
- **Checkout enqueues:** `POST /orders` now puts the order on `orders:pending`, which the worker
  charges. The worker keeps orders in sequence by retrying a failed one at the head.
- **The worker is patchable** like the API: its source and `config/worker.env` are a repo in the
  shell, deployed with `devgrill deploy worker`. The fault's config change is a real commit in
  that repo.
- **New metric:** `orders_lag_s`, the age of the order being charged, charted as "Oldest order
  waiting".

**Platform pieces:**
- **Per-service history:** deploy history entries take an optional `service`, so the worker's
  repo no longer shows the API's commits. The other drills' history is pinned to `api`.
- **Service picker:** the Code and Deploys panels now pick the service when an incident has
  more than one to edit (a labelled group of pressed-state buttons). Each service gets its own
  file list, history and confirmation. Unsaved edits are saved before switching.
- **Two invariant probes**, run from the probe container:
  - `orders-flow` places 20 orders and requires them paid within 15 s, with no order pending
    for over a minute.
  - `poison-guard` puts its own bad message at the front, places 5 orders, requires them paid
    and the bad message dead-lettered, then removes its message.

**Tuning:** the reference fix first took 130 s to drain the backlog, because the worker cleared
only about 12 orders/s more than arrived. Halving the pretend payment call to 10 ms brought
mitigation to 50 s.

**Checks:** in Docker, the break paged within 6 s and stayed broken; the reference fix mitigated
in 50 s and passed every probe. The five approaches gave their declared outcomes:
- bounding retries, rolling the worker back and dead-lettering invalid orders: all full;
- removing the message by hand: partial, failing only `poison-guard`;
- clearing the queue: fails, with 78 orders left pending forever.

The table-lock drill's cheat patch was regenerated for the new `place_order`, and that drill was
retested with all its approaches.

### Drill 5: Bestsellers are down (deploys/bad-config, SEV2)

**The incident:** a config deploy adds `DB_STATEMENT_TIMEOUT_MS=2`, copied from staging, where
"2" meant seconds.
- Small products' queries finish within 2 ms. A bestseller's rating summary aggregates 30,000
  reviews and needs tens of milliseconds, so Postgres cancels it every time, and it is never
  cached.
- The five featured products and search return 503, while obscure products load.

**Fixes:** set 2000, roll back, or turn the timeout off. Flushing the cache changes nothing.

**Base-app work (ShopKart):** a `DB_STATEMENT_TIMEOUT_MS` setting (default 0, so no other drill
changes), and a 503 with a "query cancelled" log line when it fires. The table-lock drill's
config patches gained the new trailing lines as context.

**Found by running it:** "raise it to 20 ms" was meant to fail, but it passed. The bestsellers'
query takes about 185 ms only on a cold read; warm, it fits under 20 ms. That approach was
replaced by the flush, which fails deterministically.

**Checks:** in Docker, the break paged within 6 s and stayed broken, and the reference fix
mitigated in 1 s and passed every probe. The approaches gave their declared outcomes:
- set 2000, roll back, turn it off: all full;
- flush the cache: fails;
- the cheat that leaves ratings out: fails on correctness.

### Drill 6: Search pins the CPU (memory/runaway-regex, SEV2)

**The incident:** a deploy checks search queries with `^([A-Za-z0-9]+\s?)*$` before stripping
punctuation.
- On a few words ending in punctuation, the nested quantifiers try every split of the letters,
  doubling with each letter: "waterproof hiking jackets mens!" takes over a second.
- Python's `re` holds the GIL throughout, so the whole API worker freezes, and so does every
  request on it.
- Two of 40 search terms in the traffic have that shape, which is enough for a p99 over 1 s.
- **Tuned on CI:** the first terms cost about half a second each here. GitHub's runners are
  2 to 3 times faster per core, so p99 peaked at 490 ms there and the drill never paged. Two
  more letters (four times the work) fixed that.

**Fixes:** a pattern that can't backtrack (`^[A-Za-z0-9]+( [A-Za-z0-9]+)*$`), dropping the
check, or rolling back. Caching search results is partial: today's slow queries are cached,
but a new one still freezes a worker.

**Base-app work (ShopKart):**
- The slow-request log line now carries the query string, so the slow searches are visible.
- The load script takes `SEARCH_TERMS`: a comma list, picked at random (the default stays
  `Trail`).

**New probe:** `any-query` sends three searches nobody has sent before (four random words
ending in punctuation), and each must answer within 1 s.

**Checks:** in Docker, the break paged within 7 s and stayed broken; the reference fix mitigated
in 1 s and passed every probe. The approaches gave their declared outcomes:
- linear regex, drop the check, roll back: all full;
- cache searches: partial, failing only `any-query`;
- the cheat that turns search off: fails on correctness.

### Drill 7: Stale prices (caching/invalidation, SEV4)

**The incident:** a "perf" deploy replaces the cache delete on a price change with a push onto
`cache:invalidations`, for an invalidation worker nobody built.
- Merchandising reprices the bestsellers about twice a second, and their cached pages keep the
  old price for the full five-minute TTL.
- Checkout charges the new price from Postgres.
- Paged on correctness, not speed: the share of orders charged a different price than the
  cached page showed.

**Fixes:** invalidate on write again, or roll back.
- **Not fixes:** a 5-second TTL still shows wrong prices for seconds after every change; TTL 0
  sends every read to Postgres (the `db-offload` probe, as in TTL zero).
- **Cheat:** recording every order as a match quiets the page but fails the freshness probe.

**Base-app work (ShopKart):**
- **Checkout compares prices:** it compares the charged price with the cached product page
  (`checkout_price_checks_total`, charted as "Orders charged a different price").
- **Pricing job in the traffic:** the load script takes `PRICE_UPDATE_RATE` (the share of
  iterations that also reprice a hot product; default 0).

**Found by running it:** "TTL 0" and "TTL 5 s" first left stale prices on the page during
verify. A new TTL doesn't shorten entries already cached, so both approaches now flush the
cached products after the config change, as a player would. With the flush, TTL 0 then passed
every probe: at this load Postgres serves the bestsellers uncached. The goal says the cache
must keep carrying the load, so the drill gained TTL zero's `db-offload` probe.

**Deploys and config is published,** now that it has playable drills:
- **Quick Fire:** eight cards for the track (3 warmup, 3 core, 2 hard), as every published track
  needs.
- **Onboarding:** the calibration deals one card per track, so seven now. The request allows up
  to 12 answers (it was capped at 6). The offer screen reads "one Quick Fire card for each
  track" instead of "six cards".
- **Found by CI:** the Bestsellers drill was hidden from the catalogue while its track was a
  draft (a pagination test caught it).

**Checks:** in Docker, the break paged within 7 s and stayed broken; the reference fix mitigated
in 7 s and passed every probe. The approaches gave their declared outcomes:
- invalidate on write, roll back: full;
- a 5 s TTL, and TTL 0: both fail;
- the quiet-the-check cheat: fails.

## Gate checklist (docs/PLAN.md, Phase 7), so far

- [ ] All 20 scenarios pass `devgrill-content test` nightly (7F).
- [ ] Each scenario playtested by someone other than its author (7F).
- [ ] Time-to-first-win on `/try`: the flow is built (7B). It still needs 5 new users, median under 5 minutes.
- [ ] Daily rollover across time zones; share card with no spoilers; pre-warm pool.
  - Done in 7A: the rollover and the share card.
  - Owed: the pre-warm pool, and the card in dark mode (OG images are light only).
- [x] Streak logic property-tested (time zones, DST, freezes, leave days); notification caps enforced (7D).
- [x] Admin RBAC: authors can't publish; reviewers can't edit content; every admin action is audit-logged (7E).
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
