# 014. Gateway, in-sandbox control and telemetry (phase 4)

Date: 2026-10-20 · Status: accepted

## Context

Phase 4 puts a person in front of a live sandbox: a terminal, logs and metrics as they happen,
the database and cache from the inside, code they can edit and deploy, and teammates who
react. The browser must reach all of that without ever getting a route into the sandbox. The
sandbox must not get a route out either: no egress, and the platform unreachable (ADR 012). And
whatever the player does (in the UI or in the terminal) must land in one trail, for the
timeline now and for scoring and the AI later.

## Decisions

### The pieces

```
browser ──HTTPS──▶ web (Next) ──/api/v1/* proxy, adds the JWT or guest token──▶ API
   │                                                                  │ signed HTTP
   │ WSS + single-use ticket                                          ▼
   └──────────────────────────────────────────────────────────────▶ gateway ──Docker API──▶ sandbox
                                                                      ▲
worker (Temporal): monitor activity ──samples──▶ Valkey ──pub/sub─────┘
```

1. **The web app is the only door for the browser's REST calls.** `/api/v1/[...path]` is a
   same-origin route handler. It adds the caller's credentials on the server (the user's JWT,
   or the guest token from its httpOnly cookie) and streams the answer back, SSE included.
   - The browser never holds an API token.
   - Cookies authenticate this route, so it refuses cross-site requests that change state:
     Origin must match, `Sec-Fetch-Site` must not be cross-site. That is the CSRF guard.
2. **The gateway** (`apps/gateway`) is the only platform service besides the worker with
   Docker access. On a hosted fleet it runs on each sandbox host. It serves:
   - **Two browser WebSockets**, the terminal and telemetry, opened with **single-use tickets**:
     - 32 random bytes in Valkey for 60 s, deleted by the first read (GETDEL);
     - bound to one attempt, one owner and one channel;
     - issued by `POST /v1/attempts/{id}/ws-ticket` after the API checks ownership;
     - Origin is checked too (cross-site WebSocket hijacking).
     - Refusals accept, then close with a code (4401 bad ticket, 4403 origin, 4409 not ready,
       4410 ended). A refusal before accepting reaches browsers as a bare 403, and clients
       couldn't tell "wait" from "give up".
   - **Internal sandbox operations for the API** (`/internal/attempts/{id}/...`): files,
     deploy history, deploy, rollback, restart, database and cache insights. They are signed
     with HMAC over **method, path and query, and body**, so a captured GET can't be replayed
     against another endpoint.
   - **The control bridge** for the in-sandbox CLI (below).
3. **The worker's monitor activity** samples every attempt's metrics every 2 s, as long as the
   attempt is live.
   - It pushes each sample to a Valkey list (30 minutes of history, for reloads and the
     debrief) and a pub/sub channel. The gateway forwards these to telemetry sockets.
   - It detects mitigation: **the SLO breached at least once, then held for `slo.for_s`**. A
   service that was healthy from the start isn't "mitigated".
   - It detects regression: unhealthy for 20 s after being mitigated.
   - It signals the workflow, which moves the attempt between `active` and `mitigated`.
   - Sampling happens once per attempt, not per open tab, and detection works with no
     browser open.

### The in-sandbox CLI without a network route out

The `devgrill` CLI in the player's shell calls `http://control:7000`. That name is an alias of
the platform-owned probe container, where `dg-relay` listens. The relay forwards each request
to the gateway as a JSON line on its own stdout. The gateway holds that process's stdin and
stdout through a Docker exec, runs the request with the same operations the UI uses (source
`cli`), and writes the answer back as a JSON line.

- **The sandbox network stays `internal`.** The only way out is an exec channel that the
  platform opened from the outside.
- **The relay exits when its stdin closes**, so a restarted gateway starts a fresh one.
  Stopping a stale relay uses a pattern anchored to its exact command line, because an
  unanchored `pkill` matches the shell that runs it.
- **Requests run concurrently**, so a slow deploy doesn't block `devgrill status`.

### Operations and the trail

`Operations` (in the gateway) is the one implementation behind the UI and the CLI:
- validate against the base app (the shell isn't a service you restart; only patchable
  services deploy; rollbacks take a commit SHA);
- act through the driver;
- record the result.

Every mutating action becomes an `attempt_events` row with its beat trigger
(`api.deployed`, `postgres-db.restarted`...), through `EventRecorder`.
- **Deploys** also store their diff against the live commit (`code_changes`).
- **Console queries** go to a hidden `trail` event.
- **What is live** is a git ref in the service repo (`refs/deploys/live`).

### Events and the war room

`attempt_events` is the incident's single stream. The workspace builds the timeline, the war
room, the boot sequence, state, hints and extensions from SSE. Specifically:
- **Hidden types** (`fault` names the injected fault; `health` and `trail` are bookkeeping)
  never reach the player.
- **Beats** fire exactly once:
  - time-based beats (`at:`) on workflow timers;
  - event-based beats (`when:`) wherever the event is recorded.
- **Player status updates** are events, and are also rows in `war_room_messages` (phase 6
  reads them).

### Sandbox-side tools for the panels

The probe image gains:
- **`dg-sql`:** one statement as the base app's read-only role (`readonly_user`), in a
  read-only transaction, with a 5 s timeout and 200 rows max. It runs the Database panel's
  insights (pg_stat_statements, connections, blocked sessions) and its console.
- **`dg-cache`:** cache stats, a key sample, and a 1.5 s `MONITOR` window that shows which
  keys clients ask for and whether each exists. "Asked for but missing" is how a key-format
  change shows itself.

### Terminal

- `tmux new-session -A` in the shell container, so a reload re-attaches.
- Binary frames carry keystrokes in and screen bytes out; text frames carry control messages.
- Each session is recorded as asciicast v2 to object storage, with a SigV4 client small enough
  to avoid a full SDK, plus a `recordings` row. The save is shielded from disconnect
  cancellation.
- The cursor doesn't blink: nothing animates on streaming panels.

### The workspace in the browser

- **One `WorkspaceSource` interface with two implementations:**
  - **live:** the proxy, SSE, and the gateway sockets;
  - **demo** (`/incident/demo`): canned data, so the design shell, accessibility and keyboard
    tests run without Docker.
- **External stores** (`useSyncExternalStore`): telemetry samples (a ring of 900) and logs (a
  ring of 2,000) re-render only the panels that draw them.
- **Lazy loading:** xterm.js, CodeMirror and uPlot load with their panels. The route's initial
  JS is 253 KB gzipped (budget 450 KB, `apps/web/scripts/route-budget.mjs`).

## Consequences

**Positive:**
- No new network path into or out of a sandbox.
- One trail for UI and CLI actions.
- Mitigation is detected from the system itself, not claimed. A "declare mitigated" is
  scored against the detected state.

**Negative:**
- The gateway holds an exec stream per attempt with a terminal open.
- Telemetry sampling costs about one probe exec every 2 s per live sandbox, which is fine at
  local scale. At fleet scale it would move to an in-sandbox agent pushing metrics
  (VictoriaMetrics, PLAN §12.3).

**Follow-ups:**
- Phase 5: verify scoring and the debrief (it uses the recordings and the sample history).
- Phase 6: LLM teammates reply in the war room.
- Track H: gateway TLS, per-host gateways, and a ticket bound to the gateway host.

## Alternatives considered

- **A second, non-internal network for the probe, with the relay talking HTTP to the
  gateway.** Rejected: it gives a container on the sandbox network a route to the host.
- **Browser straight to the API with a token in JS memory.** Rejected: the token would be
  readable by any script on the page, and guests' httpOnly cookie couldn't be used.
- **Telemetry sampled by the gateway per WebSocket.** Rejected: N tabs would mean N scrapers,
  and mitigation detection would stop when nobody is watching.
