# 017. Public surfaces and the Daily rotation (phase 7)

Date: 2026-10-27 · Status: accepted

## Context

Phase 7 adds the first things a player shows to other people: a public profile and a share card
for a solved drill. It also makes the Daily drill a scheduled pick instead of a lazy one. Each
needs a rule that holds up without anyone watching.

## Decisions

### Public profiles are opt-in

New profiles start private (`is_public` defaults to `false`, migration 0005). Before 0005 the
default was `true`. Existing rows keep their value, because flipping someone's choice is worse
than an old default.

- A private profile is a 404 to everyone except its owner, who sees it as others would if it
  were public.
- The setting lives in Settings, under "Public profile".

### Share cards are public by capability link

`GET /v1/share/{attempt_id}` returns a resolved attempt's result to anyone, without auth. The
attempt id (a UUIDv7) is the only key, and only the person who played has it until they share it.

- **Spoiler-free by construction:** severity, the scenario's title, the time from alert to the
  verified fix, and the number of hints. Never the cause, the fix, the approach or the score
  breakdown.
- **Anonymous:** nothing about who played: no handle, no rating.
- **Scope:** unresolved attempts share nothing (404). A resolved result never changes, so the
  response is cacheable for a day.
- **Daily results:** an attempt started inside that day's Daily window, on the Daily's scenario,
  carries `daily_on` (the IST calendar day).

The web page `/share/[attemptId]` is `noindex`. Its Open Graph image is rendered with Next's
`ImageResponse`, using hex values that mirror the light tokens (the colour check allows that
file).

### The Daily rotation

- **The pool:** published scenarios whose current version is playable and not opted out
  (`daily: false` in scenario.yaml).
- **Daily picks:** one shuffled cycle through the pool per pool length. Each cycle is seeded by
  its number, so every API process agrees without coordination. When a cycle would start on the
  previous cycle's last pick, the first two are swapped, so no two consecutive days repeat.
- **Weekly picks:** the same scheme, counted in weeks.
- **Creation:** the Temporal schedule `challenge-rollover` (cron `1 0 * * *`, Asia/Kolkata)
  creates each window's challenges a minute past midnight. The API still creates a missing
  window's challenge on first read, so a missed run costs nothing.

### Primers are Markdown files

Topic primers live in `content/primers/<track>/<topic>.md`, not inline in tracks.yaml.

- **Loading:** the content loader attaches them, and a primer for a topic that doesn't exist
  fails validation.
- **Limit:** 6,000 characters each.
- **Rendering:** the web renders a small Markdown subset (headings, paragraphs, lists, bold,
  inline and fenced code) as React nodes, never as HTML.

### Quick Fire answers are checked by the API

- **Content:** cards are files in `content/quickfire/<track>.yaml`, upserted by slug (migration
  0006 adds the slug).
- **Rating:** a card's level only sets its starting rating; after that, play owns it.
- **Answers:** a deck never carries the answers. Each answer goes to
  `POST /v1/quickfire/cards/{id}/answer`, which returns whether it was right, the answer and
  the explanation.
- **Access:** Quick Fire needs no sandbox, so it is open to everyone (ADR 013).
- **Runs:** runs are not stored yet. Run ratings and streak credit come with Phase 9's Quick Fire
  and wave 7D's streaks.

### Onboarding calibration seeds starting points, not ratings

- **Flow:** onboarding asks for experience (required) and role (optional), then offers one card
  per published track.
- **Starting points:** `devgrill.domain.calibration` turns them into a starting rating per track:
  - a base by experience (1350 to 1650);
  - a 100-point step up or down per card;
  - a high deviation (300 answered, 330 from experience alone).
- **Never overwrites:** a track the player already has a rating for keeps it, so onboarding
  can't be repeated to inflate a rating.
- **Not shown:** starting points have no games, so they aren't shown as ratings (track pages,
  profile and `/me/ratings` show tracks played at least once). They only shape the first rated
  game.
- **When it's offered:** sign-in offers onboarding once, to accounts with no experience level
  that haven't skipped it (`prefs.onboarded`).

### Streaks: earned freezes and on-call leave, all derived

The streak is still recomputed from `activity_days`, never incremented. The history is
replayed oldest first:

- **Freezes:** every 7 active days in a row (4 weeks in weekly mode) earns a freeze, holding at
  most 2. A missed period spends one automatically. Freezes are never sold or granted by
  hand; `streaks.freezes` is derived.
- **On-call leave** (`leave_days`, booked from today up to 90 days ahead) is neutral: it neither
  extends nor breaks the run. In weekly mode, only a whole week of leave counts as leave.
  Leave can't be booked in the past, so a missed day can't be excused after the fact.
- **Quick Fire:** any answer from a signed-in player counts as that day's activity.

Property tests cover the rules:
- freezes only help, and more activity or leave never shortens a streak;
- today, still in progress, never breaks it;
- one play per local day across DST changes stays unbroken in four zones.

### The daily email: opt-in, capped by the database, paused in one tap

- **Opt-in:** the email is off by default, like public profiles. It goes to the GitHub email
  the sign-in hook now stores on the profile (`profiles.email`). It is only used for this email
  and never shown.
- **Rules** (`devgrill.domain.digest`): the player picks a send hour (08, 09, 13, 18 or 21,
  local time). The email is never sent between 22:00 and 08:00, and at most once per local day.
- **Sending:** a Temporal schedule sweeps hourly. Each send first inserts a row into
  `notifications_sent`, keyed by user, kind and day. Only an insert that succeeds goes on to
  send, so retries and concurrent sweeps can't send twice. A send that fails after its claim
  is skipped for that day.
- **Mail port:** `devgrill.infra.mail` (SMTP; Mailpit in dev). A provider is another adapter.
- **Pausing:** every email has a pause link with an HMAC token for that user, which can do
  nothing else.
  - The page asks for one tap, because link scanners open links.
  - `List-Unsubscribe` with `List-Unsubscribe-Post` gives mail clients RFC 8058 one-click
    unsubscribe, through a token-only web route.

### The content console: roles, lifecycle and audit

Content is edited in git, so the console never edits content itself. It moves scenarios
through their lifecycle and shows what play says about them.
`devgrill.domain.admin` holds the rules.

**What each role can do:**

| Role | Can do |
| --- | --- |
| author | See the console and analytics; submit a draft for review |
| reviewer | Send back (with a reason), publish, retire and restore; review unrecognised fixes |
| admin | Everything above, plus AI spend, user lookup, role changes and the audit log |

So authors can't publish, and reviewers can't move content into review.

**How it's enforced:**
- The API checks each action, and the console only shows the buttons a role allows
  (`GET /v1/admin/me`).
- A lifecycle action writes its audit entry in the same transaction, recording the from and
  to states and any note.
- So does each role change and each review decision on an unrecognised fix.

**Who owns status:** the status in a scenario file only applies when the seed first creates
the scenario. After that the console owns it, so a re-seed can't undo a review decision.

**Validation reports:** `devgrill-content test` writes `.reports/<slug>.json`. The seed
attaches it, without the samples, to the current version, and the console shows passed,
failed or none.

**Analytics** cover finished runs on all versions: solve rate, leavers, median time, hints
and rating drift. Flags appear only from 10 runs on.

## Consequences

- An old public link to a profile created after 0005 doesn't exist until its owner opts in.
- A shared link can't be revoked, short of deleting the attempt. The card holds nothing private,
  so that is acceptable.
- The catalog list reads `playable` with a join on the current version, inside the existing
  20 ms query budget.
