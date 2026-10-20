# 013. Access tiers and the sandbox budget

- Status: accepted (2026-10-20)
- Deciders: owner
- Related: ADR 007 (sandbox driver), ADR 011 (data and auth), PLAN §12.4, §17, §19

## Context

Almost all of DevGrill's running cost comes from two things: live sandboxes (about 8 containers
and 1–2 GB of RAM for up to 45 minutes) and LLM calls. Everything else (cards, briefings,
profiles, debriefs) costs close to nothing. The owner wants:

- content that needs no sandbox to be free;
- live sandboxes mostly behind a paid plan;
- a hard guarantee that nobody, free or paid, can run up the bill.

Research (2026-10-20, sources in PLAN appendix H) on comparable lab platforms:

- **Content is free; sandbox time is metered.** iximiuz Labs gives free users 1 hour a day, 1
  playground at a time, and egress to safe domains only. SadServers gives "a selection of
  scenarios with daily limits" and no outbound internet. Killercoda gives 1-hour sessions
  behind a captcha. TryHackMe gives 1 hour a day of AttackBox.
- **None of them wall sandboxes off from free users entirely.** Free users get a capped taste
  of the paid thing. Conversion for developer-sold freemium is about 5% at the median, and
  edtech is lower (2–3%).
- **Compute is cheap and abuse is the real risk.** A Hetzner AX41 (64 GB, about €50/month
  after the April 2026 price rise) works out to about €0.01 per sandbox-hour at 30%
  utilisation, so under ₹1 for a 45-minute session. Mining gangs create thousands of GitHub
  accounts (PURPLEURCHIN), so a GitHub login alone is not a gate. Egress blocking is the main
  defence everywhere.
- **Payments.** Stripe India is invite-only for new businesses. Razorpay supports UPI Autopay
  and card mandates (no re-authentication up to ₹15,000 per debit). Paddle acts as merchant of
  record for Indian sellers and handles GST and VAT.

## Decision

### Three content formats

| Format | Sandbox | Cost per play | Free plan |
|---|---|---|---|
| **Quick Fire cards** | no | ~0 | unlimited |
| **Case files** (static incidents): recorded logs, metrics, deploys and code from a real run of a live scenario. The player names the root cause, the first mitigation and the durable fix | no | ~0 (plus an optional AI review) | unlimited |
| **Live incidents** | yes | sandbox-minutes + LLM | a weekly allowance |

Case files are generated, not hand-written. `devgrill-content record <scenario>` boots the
live scenario, captures the evidence at fixed moments, and writes a case file package. Every
live scenario can yield a case file, so the free library grows with the paid one (Phase 7).

### Scenario access

Each scenario declares `access: free | pro` (spec v1 field, default `pro`):

- **Free:** the tutorial track and a few marked scenarios per track.
- **Daily Incident:** playable by every signed-in user on its day, whatever its access; it
  counts towards the free weekly allowance. This is the habit loop, and its sandbox is
  pre-warmed.
- **Guests (`/try`):** only the tutorial scenario. One live session per guest token, and a
  per-IP daily cap.

### Plan limits (initial values, stored in `entitlements.limits`, code defaults in
`devgrill.domain.entitlements`)

| Limit | Guest | Free | Pro |
|---|---|---|---|
| Live scenarios | tutorial only | `access: free` + the Daily | all |
| Concurrent sandboxes | 1 | 1 | 1 |
| Live starts | 1 per token | 3 per week | fair use: 10 per day |
| Sandbox minutes | 20 | 120 per week | 240 per day |
| Session TTL / idle | 20 / 5 min | 30 / 8 min | 60 / 10 min |
| `extend` | no | no | +15 min, twice |
| AI teammate messages | 10 | 20 per day | 200 per day |
| AI postmortem reviews | 0 | 2 per week | 20 per day |

Weeks and days roll over at 00:00 IST, like the streaks. Minutes are counted from `active`
to teardown; provisioning time is tracked but not charged to the player.

### The bill guarantee: four independent layers

1. **Per sandbox:** cgroup limits on CPU, memory and pids; no egress; TTL and idle teardown
   that is guaranteed by the Temporal workflow's `finally`.
2. **Per user:** the plan limits above, enforced on the server at `POST /v1/attempts`. A
   locked card in the UI is not security.
3. **Fleet:** `SANDBOX_MAX_LIVE` (local capacity) caps concurrent sandboxes. Above it, starts
   queue or get a 503 `capacity` with `Retry-After`.
4. **Money:** `SANDBOX_DAILY_MINUTES_BUDGET` caps the total minutes that free and guest users
   can use per IST day. At 80% an alert fires. At 100%, free starts pause until midnight with
   an honest message ("Free sandboxes are full today. Case files and cards are open."). Pro
   is unaffected up to fleet capacity. A matching LLM budget comes in Phase 6. A kill switch
   (`SANDBOX_FREE_STARTS=false`) stops free starts at once.

Errors are problem+json:

- `403 upgrade_required` when the scenario is not in the plan;
- `429 quota_exceeded` with `Retry-After` set to the next rollover;
- `503 capacity` or `503 budget_paused` with `Retry-After`.

### Abuse (hosted only, Track H)

- No egress for every plan; free and paid alike stay sealed.
- Live sandboxes need a GitHub account at least 30 days old. Cards and case files don't.
- Turnstile on guest starts.
- A mining heuristic: sustained CPU over 90% in the shell container for 5 minutes ends the
  session and flags the account.
- Card verification only if abuse appears.

### Pricing direction (still decided in Track H)

- **Regional pricing:** about ₹249/month or ₹1,999/year in India; about $8/month or $60/year
  elsewhere. This sits between iximiuz (about $4) and SadServers ($9), with annual billing
  about 35% cheaper.
- **Providers:** Razorpay (UPI Autopay, cards) for India and Paddle as merchant of record for
  the rest of the world. Stripe only if India onboarding reopens.
- **Revenue planning:** model on 2–3% conversion.

## Consequences

- **Positive:**
  - The free tier costs almost nothing, still shows the product's hook, and grows
    automatically through generated case files.
  - The worst-case monthly bill is bounded by configuration, not by user behaviour.
- **Negative:**
  - A third content format (case files) to build and maintain.
  - Quota logic touches attempts, the Daily, guests and the UI.
  - Some honest "come back tomorrow" moments for free users.
- **Follow-ups:**
  - Phase 3: the `access` field, the `devgrill.domain.entitlements` policy, enforcement in
    `POST /v1/attempts`, fleet and budget caps, minutes metering.
  - Phase 4: lock states and quota display in the UI.
  - Phase 6: the LLM budget.
  - Phase 7: case files and `devgrill-content record`.
  - Phase 9: plan management UI.
  - Track H: payments, Turnstile, the account-age gate, mining detection.

## Alternatives considered

- **No sandboxes on the free plan.** Rejected: the live sandbox is the differentiator, and
  free users who never feel it have no reason to upgrade. Every comparable platform gives a
  capped taste instead.
- **Time-only metering (iximiuz-style 1 hour a day, all content).** Rejected for now: it makes
  every pro scenario free in small doses and weakens the paid library. Kept as a fallback if
  conversion data says otherwise.
- **Card verification for every free user.** Rejected: hostile to students, who are the core
  Indian audience. Kept as a lever if abuse appears.
