# 018. Case files: recordings, three questions, no sandbox

- Status: accepted (2026-11-04)
- Deciders: owner
- Related: ADR 012 (scenario spec), ADR 013 (access tiers), ADR 015 (verify and scoring), ADR 016 (AI layer), PLAN Phase 7

## Context

ADR 013 made case files the free, sandbox-less format: a recording of a real run of a live scenario, with the player naming the root cause, the first mitigation and the durable fix. It left the mechanics open. Three questions mattered:

- how a recording stays honest, when nobody re-runs it after it is made;
- how the workspace shows a recording without a second set of panels;
- where the content lives.

## Decision

### Two files per scenario

`content/scenarios/<track>/<slug>/case-file/`:

- **`case.yaml`, written by hand:** the three questions with their options, answer and explanation; the commands to capture; and the clues the answer rests on.
- **`evidence.json`, generated:** `devgrill-content record <slug>`. Never edited.

Generated evidence is committed. Regenerating all 20 takes about an hour of real sandboxes, and the app needs it at run time with no Docker.

### A recording is the reference test's first half

`record` reuses `_break` and `_stays_broken` from `devgrill-content test`:

```
boot → faults → load → BREAKS (first capture) → left alone → STAYS BROKEN (second capture) → destroy
```

It refuses to write anything if the scenario doesn't break as declared, or recovers by itself, or is over by the end: most of its last three samples must still miss a target. That last check is stricter than the reference test, which only asks that the target doesn't hold for `for_s` inside its window, so a drill healing near the end passes it. The first batch of recordings had one like that. So a recording is always of an incident that really happened on the real system, still going when it ends. Nothing is fixed in it.

Where the evidence takes longer to show than the incident takes to break, `hold_s` in `case.yaml` keeps watching before the last capture (a leak reaching its memory limit).

It captures what the panels show: the metric series, up to 200 log lines per service at each capture, the deploy history with each diff, the source of each deployable service, Postgres and cache insights, each service's state, and the commands in `case.yaml`. Sandbox names are replaced, because they differ on every recording and mean nothing to a reader.

### Honesty checks that need no sandbox

`devgrill-content validate`, and so CI, checks each playable scenario:

- **It has a case file.** Every live scenario ships one (PLAN Phase 7).
- **The evidence shows the clues.** Each clue names a panel and a string that must appear in that panel's part of the recording. A case file can't ask for something its evidence doesn't show. This catches a recording that missed the moment, and a question edited away from what the evidence says.
- **It ends still broken,** by the same rule the recorder uses.

These can't tell whether a capture is any use. A human read of all 20 found an empty capture and a query that didn't match its title, both of which passed. Read the output of anything you record.

Staleness is only a note. `evidence.json` holds a hash of the scenario, its faults and the base app's version; a change prints a note in `validate`, and `record --stale` re-records those. It doesn't fail the build, because the recording is still a true record of the version it came from, and failing would make every fault edit wait on an hour of sandboxes.

Two checks stop the answer standing out: the API shuffles options per case and question (a stable hash, so a reload doesn't move them), and a test fails when the right option is more than 12 characters longer than the longest wrong one. Wrong options come from the scenario's `approaches/` where they can, so most are tested in real sandboxes to fail.

### One workspace, a third source

The workspace's panels only see the `WorkspaceSource` interface. A case file adds a third implementation next to `live` and `demo`: `recording`. It moves all times so the incident ended just now, so charts and "5 min ago" read naturally however old the recording is.

Panels hide what can't work on a recording (save, deploy, roll back, restart, the query console, freeze), and they don't poll. A case file has its own small shell rather than a flag through the live one, which is mostly hints, the clock, verify and overlays. It shares the tool list, the panels and the layout. Questions sit where the war room sits, and the recorded commands sit where the terminal sits.

### Read from the content folder

The API reads case files from `content_root`, as it already does for a scenario's bundle. There is no `case_files` table.

- **Why not the database:** a recording is 200 to 350 KB, 20 of them are about 5 MB, and `seed` runs before each integration test. Nothing would query inside them.
- **The evidence endpoint** sends the stored file as it is, with an ETag and a five-minute public cache, instead of parsing and re-serialising it. The page loads it in the browser, so a few hundred KB don't go into the server-rendered HTML.
- **The lifecycle stays in the database:** a case file shows only while its scenario is published and playable, so retiring a scenario retires its case file.

### Scoring and what is kept

- **Deterministic:** root cause 50, mitigation 25, fix 25. Naming the cause is worth the most because the other two follow from it.
- **Signed-in players:** the first answers are kept in `app.case_file_plays`. After them the answers are known, so a second try returns the first result. Answering counts as the day's streak activity (kind `casefile`), like a Quick Fire answer.
- **Guests:** get the same scored result, and nothing is kept.
- **Ratings don't move.** A multiple-choice reading isn't the skill the rating measures, and the ratings stay comparable if they only come from live incidents.

### The optional write-up

A signed-in player may explain it in their own words and get a short AI read, once per case file. It is synchronous, like a nudge, rather than a workflow like a postmortem review: it is one small call with nothing to settle.

It counts against the plan's `postmortem_reviews` allowance, so postmortems and case files share one count, as ADR 013 says. It shares the `ai_grading` flag and has its own feature name (`case_review`) for cost and metering. It runs only after the answers are out, so it has nothing to spoil and no spoiler check. The write-up reaches the model redacted and fenced as data. With AI off the answers still work, and the panel says nothing about reviews.

## Consequences

- **Positive:**
  - The free library grows with the paid one, at no running cost: no containers, and the evidence is a static file.
  - The live workspace gained no branches for a second mode beyond small read-only checks in its panels.
- **Negative:**
  - The repo carries about 5 MB of generated JSON, and a re-record rewrites all of it.
  - A case file gives its drill away, and the reverse. The list and the briefing say so; nothing enforces it, because a player who wants to read first may.
  - A recording can go stale in small ways: a changed fault prints a note and nothing more until someone re-records.
- **Not done:**
  - The workspace is desktop-only here too, so case files offer the same "needs a bigger screen" page with Quick Fire. A phone layout is a separate piece of work.
  - The API doesn't compress the evidence; a hosted setup would do that at its proxy (Track H).

## Alternatives considered

- **Store evidence in the database.** Rejected above: it costs seed time and gives nothing.
- **Re-record in CI nightly.** Rejected: it would rewrite 5 MB of committed files every night for changes nobody made, and recordings of the same scenario differ anyway. The nightly suite already proves each scenario still breaks.
- **Generate the questions with the LLM.** Rejected: the answer key has to be right every time, and the wrong options are better taken from approaches that really fail.
- **A second try for a better score.** Rejected: after the first try the answers are on screen, so a better second score means nothing.
