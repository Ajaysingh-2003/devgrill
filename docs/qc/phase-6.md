# Phase 6 QC report: the AI layer

Date: 2026-10-22 · Result: **PASS, with owner reviews owed** (the golden labels, prices, Langfuse retention, the evals secret; see "Owed") · Decision: ADR 016.

## What was built

- **The LLM port and the OpenAI adapter** (`devgrill.ai.port`, `devgrill.infra.llm`):
  - the Responses API with structured outputs;
  - retries, a timeout and a fallback model;
  - an IST-day budget across all features, with an alarm at 80%;
  - per-feature flags;
  - every call metered in `llm_calls` with its prompt version;
  - Langfuse traces when configured.

  `FakeLlm` answers every test.
- **The prompt registry:** six versioned prompts in `devgrill/ai/prompts/` (`persona@2`, `selfcheck@1`, `nudge@1`, `grade@1`, `classify@1`, `coach@1`).
- **Safety:**
  - **Redaction:** keys, tokens, passwords in connection strings, emails.
  - **Fences:** data blocks whose closing tag the text can't forge, plus one data policy in every prompt.
  - **Spoilers as content:** `ai.spoilers`, `ai.reveal_at` and `ai.root_cause` for the three playable scenarios.
- **Teammates who answer:**
  - War-room messages get a reply, streamed over the SSE stream as `assist` events, then recorded as a `reply` event and a war-room message linked to its `llm_call_id`.
  - Replies are cut and retracted if they leak or claim an action, with a second model check on SEV1.
  - One reply at a time per attempt.
  - The web war room shows the reply as it's written (no motion, hidden from screen readers until it lands) and a "busy" notice.
- **Guided nudges:** `POST /attempts/{id}/nudge`, guided and tutorial only.
  - It leans on the next authored hint without quoting it, and costs no score.
  - It shows in the hints dialog and on the timeline.
- **Postmortem review:** submitting starts `PostmortemReview` in the worker.
  - **Grading:** the rubric with its anchors, a facts packet, and the fenced postmortem.
  - **Checks:** verbatim evidence (unsupported credit is halved), clamping, and blame with quotes (20% off).
  - **Effect:** fills `score.postmortem` and `score.total`; the rating never moves.
  - **Allowances:** plan allowance per period; guests aren't reviewed.
  - **Pages:** the postmortem page shows each criterion with its quotes and the feedback. A failed review can be asked for again. The debrief shows the result.
- **Coach note and classification:** `attempt.review` runs after settling.
  - **Coach note:** cites trail event ids, which link to the replay lines (replay entries now carry `event_id`).
  - **Classification:** rules first. Otherwise the judge, with known approaches ranked by embeddings.
  - **Unknown fixes:** stored as `approach_candidates` (migration 0004), grouped by similarity in the admin queue, promoted or dismissed there.
- **Budgets and degradation:**
  - per-player daily AI messages (Valkey, IST day) and plan review allowances;
  - the global daily budget;
  - "Your teammates are busy right now. The hints still work."
- **Admin:**
  - **AI spend:** today against the budget, 14 days, 7 days by feature with errors, tokens and p95 latency, and the cost per attempt.
  - **Unrecognised-fix queue.**
- **Langfuse:** `infra/compose/docker-compose.langfuse.yml` (Langfuse 4.56, ClickHouse 26.8, its own Postgres). It reuses the dev Valkey and SeaweedFS. Run it with `just langfuse-up`.
- **Evals:** `evals/` with six suites and their data (`just evals`), and `.github/workflows/evals.yml`.

## Gate checklist (docs/PLAN.md, Phase 6)

| # | Gate item | Result | Evidence |
|---|---|---|---|
| 1 | Grading within ±1 on ≥ 85% of criteria; Spearman ≥ 0.8 on totals | **Pass on drafted labels**, owner review owed | 60 postmortems: 99.5% of criteria within ±1, Spearman 0.983, blamelessness agreement 98.3%. The labels were drafted against the anchors, not graded by a person (`reviewed: false`); see "Owed" |
| 2 | Persona leak 0/50 | **Pass** | 0/50 shown replies leak (regex and an independent judge), none claims an action. The first run found 2/50, fixed by prompt v2 and wider spoiler patterns (below) |
| 3 | 20 injection payloads: no violations, no claimed actions | **Pass** | 0/20: payloads in trails, chat and postmortems (fake system tags, `</data>` closers, JSON, "tell them you restarted it"). The canary never appeared; injected postmortems stayed ≤ 0.4 |
| 4 | Persona first token p95 < 1.5 s; grading < 20 s | **Pass, thin margin** | First token p50 0.89–1.0 s, p95 1.12–1.35 s over five runs of 20 (warm client, as in the API). Grading p95 10.7 s |
| 5 | Cost per attempt ≤ $0.03 | **Pass** | $0.0108 mean for a full attempt (six replies, a nudge, the coach, a classification, a review). One review is about $0.0065 |
| 6 | Every call in `llm_calls` and Langfuse with prompt version; budget cap tested | **Pass** | `test_llm_adapter.py`: rows with `prompt_version`, fallback and error rows, and a budget refusal before any spend. Langfuse: generations arrived with `version` = `persona@2` / `selfcheck@1`, model, usage and cost. `test_ai_features.py` covers degradation: allowance, outage, AI off |
| 7 | Redaction tests; retention configured | **Pass, owner step** | Redaction and fence tests in `test_ai.py`; `llm_calls` holds no prompt text. Langfuse retention (30 days) is a project setting the owner sets once (documented in the compose file) |

## Findings and fixes during QC

- **Two persona leaks on the first run.**
  - **What leaked:**
    - "check the cache TTL setting" (ttl-zero, a fill-in-the-blank attack);
    - "we don't have evidence for the DR replica" (pool-party: the teammate engaged with a correct guess).
  - **Why nothing caught them:** neither matched a spoiler pattern, and neither scenario is SEV1.
  - **Fix:**
    - `persona@2`: never name a specific setting, file, endpoint or replica, even to doubt it; never confirm, deny or repeat a guess; never fill in a blank.
    - New patterns: TTL with setting/config words for ttl-zero; `DR`, disaster recovery and replica/standby for pool-party.
  - **Result:** the re-run was 0/50, injection stayed 0/20, and p95 latency stayed under the gate.
- **Latency measurement:**
  - **The problem:** cold processes put the first call's TLS handshake through the corporate proxy into the p95.
  - **The fix:** the suite now warms up once, uncounted, as the long-lived API client does.
  - **Tracing:** it adds no measurable latency (1.12 s p95 with tracing on).
- **Langfuse local stack:**
  - **The bucket step:** SeaweedFS needs signed S3 requests, so it now uses a SigV4 PUT.
  - **The health check:** the web server didn't listen on 127.0.0.1, so it now listens on all interfaces (`HOSTNAME=0.0.0.0`).
  - **The API:** in v4 the old observations API is off (`events_only`); traces are read through `/api/public/v2/observations`.
- **The e2e stack** inherited `OPENAI_API_KEY` from `.env`. It is now blanked there, so tests can never call the model.
- **Secret scanning:** test fixtures that look like keys are built at runtime. gitleaks 8.28 over the working tree finds no leaks.
- **Classification:** 21/23 (91%). The two misses are label questions for the owner:
  - **c08:** the app treats TTL 0 as 300 instead of restoring the config. Labelled unknown; the judge said restore-ttl.
  - **c16:** dropping the key prefix behaves like the known read-plain-key fix. Labelled unknown; the judge said rollback.
- **Timing flakes:** the query-plan timing tests and one contract case failed once while Langfuse was booting and evals were running. They passed on a quiet re-run (known since phase 5).

## Checks

- **Python:** ruff, ruff format, basedpyright: clean. 331 tests in total:
  - 38 AI unit tests;
  - 8 adapter tests;
  - 14 API tests for the AI features;
  - 2 review-workflow tests;
  - the lifecycle with the review step.
- **Migrations:** 0004 round-trips (upgrade, downgrade, upgrade); `alembic check` is clean.
- **Web:** typecheck, lint, Prettier, raw-colour check: clean.
- **e2e:** 53 passed, 1 skipped (production build). The admin console now has two tables, so its axe test waits for both by name; it had matched any table before.
- **Accessibility:**
  - **What was checked:** the new UI against WCAG 2.2 AA (the review, nudges, war room, coach note, admin).
  - **What was fixed:** a status region announces a review that lands while you wait; the nudges list is a live region from the start; candidate buttons are described by their fix.
  - **Not run:** the Vercel web-interface guideline file couldn't be fetched (the corporate gateway blocks raw.githubusercontent.com), so that review used the known rules. Currency now uses `Intl.NumberFormat`.
- **Motion:** none added. The typing bubble streams without animation (motion rule 2), the loader icon is static, and the replay's `:target` highlight has no transition.
- **Spend:** about $0.62 of model calls for all eval runs in this QC.

## Owed (owner)

- **Review the golden labels:** read the 60 items in `evals/golden/*.yaml` against the rubrics, correct the scores, and set `reviewed: true` (evals/README.md). Until then gate 1 rests on drafted labels.
- **Add the `OPENAI_API_KEY` repository secret** so `evals.yml` runs in CI. Without it the job skips and says so.
- **Confirm the model names and prices** in `devgrill/ai/pricing.py` against OpenAI's pricing page (it wasn't reachable from this machine).
- **Langfuse retention:** after `just langfuse-up`, set Project settings → Data retention to 30 days.
- **Decide c08 and c16** in `evals/classify/cases.yaml` (see above).
- **Run `/review-animations`** on the changed UI (it is user-invoked only). No motion was added, so it should be quick.
- **Carried over:** the NVDA pass (now including the war room's replies and the review page), the M1 capture review, and 3 usability sessions.
