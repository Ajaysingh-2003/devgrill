# Voice and wording

How DevGrill talks to players. The design system covers how things look (`system.md`); this covers what they say.

## Principles

1. **Keep the craft, drop our jargon.** Players are engineers practising on-call. Words they will meet on a real incident stay: p99, latency, error rate, deploy, roll back, logs, cache, connection pool, restart, root cause. Words that only exist because of how DevGrill is built go: sandbox, attempt, probe, SLO, telemetry, debrief.
2. **Say what happens next.** A button names its result ("Check my fix", not "Verify"). A message about a limit says when it lifts and what to do meanwhile.
3. **Plain and calm.** Sentence case, plain verbs, no exclamation marks, no blame. Errors say what went wrong and how to fix it; they never apologise and are never vague.
4. **One name per thing, everywhere.** If a button says "Check my fix", the dialog, the results page and the chat say "check" too.

## Glossary

| Don't say | Say | Notes |
|---|---|---|
| incident (the thing you play) | **drill** | "Start the drill", "3 free plays a week", "Recent drills". The story inside a drill can still have an outage or an incident; that's in-world. |
| sandbox, environment | **your practice system** (or just "it") | "Your practice system starts in about 30 seconds." |
| live incidents (quota) | **plays** | "You've used your 3 free plays this week." |
| sandbox minutes | **practice time** | |
| attempt | **run** | "This run doesn't change your rating." |
| Guided / Real on-call (modes) | **With hints** / **No hints** | "No hints" counts more for your rating. |
| Mitigated (button), declare mitigated | **It's working again** | The claim that the service recovered. |
| mitigated (state) | **working again** | "The service is working again." |
| Verify, verify run | **Check my fix**, **check** | |
| probes | **checks** | "4 of 5 checks passed." |
| SLO, SLO breaching | **target**, **over target** | "p99 under 500 ms" is a target. |
| telemetry | **live graphs** | |
| war room | **Team chat** | |
| debrief | **Results** | |
| postmortem | **write-up** | "Write up what happened." The headings inside stay (Summary, Impact, Root cause, Action items). |
| approach, approaches | **fix**, **other ways to fix it** | |
| replay (of the investigation) | **how it went** | |
| tear down | **shut down** | |
| guest | **without an account** | |
| quota | **limit** | |

Phase names in the workspace header: **Look → Find the cause → Get it working → Fix it properly → Check → Write up**.

## What stays technical

Code names (`attempt`, `sandbox`, `probe`, `slo` in APIs, events, files and logs) keep their names; only what a player reads changes. Admin pages are for us, so they may use internal names.

`scripts/check-copy.mjs` (`just copy-check`) flags the "Don't say" words in player-facing text.
