# Phase 4 design QC: Incident workspace

Date: 2026-10-20 · Procedure: `docs/PLAN.md` §14.5 · Screenshots: `docs/design/qc/phase-4/`

## 1. Screenshot matrix

The demo workspace (`/incident/demo`, canned data through the same panels as a live incident) is captured in light and dark at 1440, 1024 and 390 px. Regenerate with `just shots docs/design/qc/phase-4 /incident/demo` (`FORMAT=jpeg FULL=0`; in Git Bash set `MSYS_NO_PATHCONV=1`, or the path is rewritten to a Windows path).

The live workspace was reviewed in the browser during the real-stack runs (`apps/web/e2e/live-flow.mjs` saves `test-results/live-flow.png`): boot overlay, terminal, logs, charts, rollback, timeline, editor.

At 390 px the workspace is replaced by "This incident needs a bigger screen", which offers Quick Fire and the drills. That is deliberate (PLAN §8.4).

**Defects found in the screenshots and fixed:**

| Defect | Fix |
|---|---|
| The terminal took 23% of the width in the default (Triage) layout: about 290 px at 1440 and 190 px at 1024, so `git log` and `redis-cli` output wrapped mid-word | Triage is now 46 / 30 / 24. The terminal is the most-used panel, and the charts still fit two columns at 1440 |
| "Screen reader mode" wrapped onto three lines and spilled out of the 40 px panel header | The label is "Screen reader", and it doesn't wrap. `PanelFrame` keeps the title and actions at their natural width; only the meta text truncates |
| The Overview header had one pill per SLO, and at 1024 the second was clipped ("Error rate: b…") | One summary pill ("2 of 2 SLOs breaching", "Every SLO holds", "SLO: no data yet"). Each chart already draws its own SLO line and breach |

**Accepted:**
- **The terminal's status text** ("oncall@shopkart: Connected") truncates in narrow layouts. It is a `role="status"` region, so screen readers get the whole text, and the cursor and output show the connection anyway.
- **The war room composer's placeholder** clips at 1024 px. The field grows as you type.

## 2. Skill reviews

**`accessibility`** (WCAG 2.2 AA) on `apps/web/components/workspace/**`:

| # | Finding | Outcome |
|---|---|---|
| 1 | **Timing (2.2.1):** the idle timeout ended an incident with no warning | **Fixed.** Keys, clicks and scrolling touch the attempt (`POST /v1/attempts/{id}/touch`, at most once a minute, listened for in the capture phase so the terminal and editor count). A banner warns a minute before the idle limit ("Still there?… Press any key or click anywhere to keep it"). The TTL already had T-5 and T-1 warnings with Extend |
| 2 | **Focus order:** while the boot or ended overlay covered the workspace, Tab still reached the panels behind it | **Fixed.** The tool rail and panels are `inert` while an overlay shows. When the incident ends, focus moves to the ended heading |
| 3 | The terminal is a canvas | xterm's screen-reader mode (toggle in the panel header) renders output as readable lines |
| 4 | Charts are images | Every chart has a text summary (value, SLO, breach) |
| 5 | Live regions | Only the page is assertive (`role="alert"`, inserted after mount). Claims, the network, expiry and idle banners and the terminal status are polite `status` regions |
| 6 | Keyboard | Tools 1–6, ⌘K palette, presets ⌘1–4, F focus mode, `/` filter and `.` freeze in Logs, arrows in the log list, ⌘S and ⌘⏎ in the editor. The splitters are WAI-ARIA window splitters (`react-resizable-panels`). Keys inside the terminal stay the shell's: ⌘K there is "kill line", not the palette |

**`web-design-guidelines`** (from the rules; the guidelines URL is blocked by the corporate DNS filter):
- The log filter placeholder now ends with "…".
- Destructive actions (Roll back, Reset, Leave) ask first; Leave and Reset are danger buttons with text on the danger fill.
- Numbers are tabular in the clock, the hint count and the charts.

**Motion** (rules from `emil-design-eng`, `animate` and CLAUDE.md):
- Nothing animates on streaming panels: no shimmer on logs, charts or the terminal, and the terminal cursor doesn't blink.
- Keyboard actions are instant: the palette, tools and presets.
- The verify spinner stops under reduced motion (`motion-reduce:animate-none`).
- The boot sequence shows real steps, not a fake progress bar.
- **`/review-animations`** (run 2026-10-22): **Block, now resolved.** The workspace's dialogs (hints on `h`, verify on ⌘⇧V, reset and leave from the palette) animated when opened from the keyboard; they now open instantly (`DialogContent instant`). Also fixed: `transition-all` on tabs, switch and button narrowed to named properties on the tokens; the sheet's built-in `ease-in-out` replaced by the enter and exit curves; popover, dropdown, select and tooltip moved from tw-animate keyframes to interruptible Base UI transitions; the unused progress bar no longer animates width; the celebration's count-up writes a motion value instead of rendering React per frame. Kept as is: reduced motion makes route fades instant too, as the in-app setting promises.

## 3. Owed

- NVDA pass on Terminal (screen-reader mode), Logs, Timeline and War room.
- 3 moderated usability sessions (`docs/qc/phase-4.md`).
