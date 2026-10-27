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

## Consequences

- An old public link to a profile created after 0005 doesn't exist until its owner opts in.
- A shared link can't be revoked, short of deleting the attempt. The card holds nothing private,
  so that is acceptable.
- The catalog list reads `playable` with a join on the current version, inside the existing
  20 ms query budget.
