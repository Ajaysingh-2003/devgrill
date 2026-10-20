# Phase 4 performance: incident workspace

Date: 2026-10-20.

**Setup:**
- The machine from `docs/perf/phase-3.md` (Windows 11, Docker Desktop, 12 CPUs, 8 GB for the Docker VM).
- The dev stack (`scripts/dev.py`: `next dev`, uvicorn, the worker, the gateway) runs on the same machine as the sandboxes and the browser.
- Numbers from `next dev` are pessimistic for the web: no minification, React dev mode.

## Terminal keystroke echo (gate: p95 < 80 ms)

Measured in the browser: from the WebSocket `send` of a keystroke frame to the next screen frame, through web → gateway → docker exec → tmux → bash and back. Source: `apps/web/e2e/live-flow.mjs`, 41 keystrokes typed 120 ms apart.

| Run | p50 | p95 |
|---|---|---|
| Final run (after the Phase 4 fixes) | 12 ms | **68 ms** |
| Earlier runs during the phase | 5–9 ms | 12–87 ms |

The one p95 over 80 ms (87 ms) came from the first run after a cold `next dev` start, while the dev server was compiling routes on the same CPUs. The path itself is a few milliseconds; the tail is the shared machine.

## Telemetry (gate: sample-to-chart < 2.5 s)

The worker samples every 2 s. The delay from a sample's timestamp to its arrival in the browser was at most **0.02 s** in the final run (0.23 s in an earlier one). Charts draw on arrival. The worst case a player sees is one sampling interval plus this delay.

## Time to active (Phase 3 gate: < 45 s)

| Path | Time |
|---|---|
| Browser: Start → "Getting your incident ready" gone (ttl-zero, guest) | 18–39 s across runs, with a soak's sandbox running at the same time in the slowest |

## Workspace route JS (gate: ≤ 450 KB gz initial; heavy libraries lazy)

`node apps/web/scripts/route-budget.mjs` on the production build (now a CI step): **253.8 KB gz**, which is Next's runtime plus the route's entry chunks.
- xterm.js, CodeMirror and uPlot are absent from those chunks; they load with their panels.

## Soak (gates: 30-minute terminal session, heap growth ≤ 20%; 1-hour telemetry stream, bounded memory)

`apps/web/e2e/soak.mjs`: Pro user, big-sale-meltdown, real on-call mode. The script:
- types a command into the terminal every 20 s;
- streams charts and logs throughout;
- extends twice (at minutes 38 and 52) to pass the hour;
- after a forced GC, records the JS heap, DOM nodes and elements per panel every minute.

**Run 1 (38 minutes).** The script stopped at minute 38 when it tried to extend: it pressed ⌘K with focus in the terminal, and the terminal rightly keeps that key (the shell's "kill line"). The script now moves focus out of the terminal first.

| Minute | JS heap | DOM nodes |
|---|---|---|
| 1 | 17.67 MB | 1,220 |
| 5 (baseline) | 18.84 MB | 1,509 |
| 30 | 19.54 MB (**+3.7%**) | 1,663 |
| 38 | 19.72 MB (+4.7%) | 1,702 |

**Terminal gate met:** +3.7% heap at 30 minutes, against a 20% limit.

**Run 2 (the full hour)** is recorded below once it completes.

**Bounded by design:**
- samples: a ring of 900 (30 minutes at 2 s);
- logs: a ring of 2,000 lines in the browser, and 2,000 in the gateway's per-socket queue (the oldest are dropped, and a `dropped` count is sent);
- the log list is virtualised;
- xterm scrollback: 5,000 lines;
- tmux history: 20,000 lines in the sandbox.
