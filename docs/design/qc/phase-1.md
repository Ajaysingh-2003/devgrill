# Phase 1 design QC

Date: 2026-10-13 · Procedure: `docs/PLAN.md` §14.5 · Screenshots: `docs/design/qc/phase-1/`

## 1. Screenshot matrix

There are 48 viewport captures: 8 templates × light/dark × 1440/1024/390. They are JPEG (q72) to keep the repo small. Regenerate them against a running build with `just shots docs/design/qc/phase-1 / /drills …` (`FORMAT=jpeg FULL=0`).

| Template | Route | File prefix |
|---|---|---|
| T1 Landing | `/` | `home` |
| T3 Drills / system map | `/drills` | `drills` |
| T4 Briefing | `/drills/caching/big-sale-meltdown` | `drills_caching_big-sale-meltdown` |
| T5 Workspace | `/incident/inc-4021` | `incident_inc-4021` |
| T6 Debrief | `/incident/inc-4021/debrief` | `incident_inc-4021_debrief` |
| T7 Postmortem | `/incident/inc-4021/postmortem` | `incident_inc-4021_postmortem` |
| T8 Quick Fire | `/quickfire` | `quickfire` |
| T9 Profile | `/u/ajay` | `u_ajay` |

The other templates (sign-in, status, daily, settings, admin, 404) are covered by the axe e2e suite in both themes, but they aren't in the screenshot matrix.

**Defects found by looking at the screenshots and fixed:**

| Defect | Fix |
|---|---|
| Chart marker labels ("deploy" at 19:58, "sale" at 20:00) collided with each other and drew over the series. uPlot had left right-alignment on the canvas | Explicit `textAlign`/`textBaseline`, a knock-out background, a flip to the left near the right edge, and staggered rows |
| Postmortem text areas used Instrument Serif for typed text. It is a display face and hard to read at body size | Inputs use the UI sans. The serif stays on headlines only (now a documented rule) |
| Quick Fire evidence broke mid-word (`(r` / `ows=…`) because of `break-all` | `wrap-anywhere`, which breaks only when a token can't fit on its own line (same fix in `LogView`) |
| `metadataBase` was unset, so OG URLs resolved against localhost with a build warning | `NEXT_PUBLIC_SITE_URL` (added to `.env.example`) |

## 2. Skill reviews

A read-only reviewer applied the vendored rubrics (`web-design-guidelines`, `accessibility`, `review-animations`) to `packages/ui`, `apps/web` and the tokens. It found 25 issues; all of them were verified against the code. "Accepted" means a deliberate deviation, explained.

| # | Sev | Finding | Outcome |
|---|---|---|---|
| 1 | High | Collapsed panels (focus mode, Postmortem preset) stayed in the tab order at 0 px width | **Fixed.** `inert` is toggled from the layout; new e2e "collapsed panels leave the tab order" |
| 2 | High | `VerifyCelebration`/`RatingDelta` used `useReducedMotion()` (OS only), so the in-app setting was ignored | **Fixed.** `useReducedMotionConfig()`; new e2e checks the OS setting, the in-app setting and full motion by recording every counter value |
| 3 | Med | Token durations went to 0 under OS reduce even when the user chose "Full motion" | **Fixed.** `:root:not([data-motion="full"])` guard, matching base.css |
| 4 | Med | `exit` easing was an ease-in curve | **Fixed.** `cubic-bezier(0.23, 1, 0.32, 1)`; PLAN §7.5 updated |
| 5 | Med | The streaming incident timeline slid entries in with main-thread `y` | **Fixed.** No animation (streaming surfaces never animate); `timelineEnter` removed; PLAN §7.5 updated |
| 6 | Med | Splitter focus showed only a 1 px colour change | **Fixed.** The 8 px hit area is tinted with the focus-ring colour on `:focus-visible` |
| 7 | Med | Theme and layout switchers claimed `radio` roles with no arrow-key pattern | **Fixed.** `role="group"` plus `aria-pressed` toggle buttons; story and e2e updated |
| 8 | Med | Tool tabs pointed at a section without `role="tabpanel"`; the tablist sat in a `<nav>` | **Fixed.** `PanelFrame tab=…` renders the tabpanel labelled by its tab; the rail is an `<aside>` |
| 9 | Med | Skip link only in the (app) shell; Quick Fire had no `<main>` | **Fixed.** Skip link moved to the root layout; Quick Fire has `main#main`; e2e checks 5 templates |
| 10 | Med | Sticky 56 px top bar could cover focused targets | **Fixed.** `scroll-padding-top: 4.5rem` |
| 11 | Med | Quick Fire `disabled` the focused button (focus dropped to `<body>`); the result was shown by colour only | **Fixed.** `aria-disabled`; icon + "Correct" / "Your pick" |
| 12 | Med | `aria-live` on the whole approach article re-read everything on each arrow key | **Fixed.** Removed; the radio announces the change |
| 13 | Med | The palette showed H, M and ⌘⇧V, but they were unbound | **Fixed.** Bound through `useHotkey`; the palette and keys share one command list |
| 14 | Low | A server-rendered `role="alert"` is often not announced | **Fixed.** Text inserted after mount |
| 15 | Low | The chart threshold label was accepted but never drawn | **Fixed.** Drawn at the line's right end on a knock-out |
| 16 | Low | Log table had no header cells | **Fixed.** `sr-only` `<thead>`. The level glyph was skipped: the level is already text ("ERROR"), not colour only |
| 17 | Low | Placeholders without "…"; inputs without `name`, `spellCheck` or `autoComplete` | **Fixed** |
| 18 | Low | `toLocaleString("en-IN")` hard-coded | **Accepted.** The product is India-first (owner decision) and pages are prerendered, so `undefined` would mean the build machine's locale. Moves to the user's locale with profiles in phase 2 |
| 19 | Low | Headings not balanced | **Fixed.** `text-wrap: balance` on h1–h3 in the base layer |
| 20 | Low | `theme-color` followed only the OS | **Fixed.** ThemeProvider updates the meta tags on theme change |
| 21 | Low | `aria-label` on a role-less div | **Fixed.** `role="group"` |
| 22 | Low | Avatar's visible "AS" not in its accessible name (2.5.3) | **Fixed.** "Your profile (AS)" |
| 23 | Low | Reduced motion zeroes opacity and colour transitions too ("gentler, not zero") | **Accepted for phase 1.** Instant is safe and simple; revisit in phase 4, when the workspace gets real transitions |
| 24 | Low | `RatingDelta` seeded state from the motion hook (hydration mismatch risk) | **Fixed.** Always starts at 0, and the effect counts up or jumps |
| 25 | Low | `scaleX` squashed the mastery bar's rounded end | **Fixed.** `clip-path: inset(… round 9999px)` |

**Verdicts after the fixes:**
- **web-design-guidelines:** pass.
- **accessibility:** pass. Axe still reports 0 violations, and the runtime issues axe can't see are now covered by e2e.
- **review-animations:** approve. Exits ease out, streaming surfaces are still, both reduced-motion paths are honoured, and the one celebration is skippable.

## 3. Token rules (§14.5 step 3)

- **No raw colours:** `pnpm colors:check` passes, with 108 UI files using semantic tokens only.
- **Tabular numbers:** applied on every updating number (base layer plus explicit `tabular-nums` on stats, timers and ratings).
- **Severity is encoded three ways:** glyph ladder (◆◆◆◆ … ◆◇◇◇), label and colour.
- **Serif never appears inside the workspace:** verified. The workspace uses only `font-sans` and `font-mono`. Serif is used only for briefing, debrief and postmortem titles.

## 4. Keyboard and reduced-motion run-through (§14.5 steps 4–5)

Automated in `apps/web/e2e/keyboard.spec.ts` (16 tests):
- the skip link on 5 templates
- ⌘/Ctrl+K palette navigation
- theme persistence
- tool number keys (ignored while typing)
- ⌘/Ctrl+1–4 presets
- keyboard splitter resizing
- F focus mode and Esc
- collapsed panels made inert
- the <1024 px fallback
- reduced motion through the OS and in-app settings, plus a full-motion control test

Every story also runs a second time in dark mode with in-app reduced motion.

No separate manual keyboard pass was done in this phase beyond these automated flows. The owner should do a quick Tab-through of landing → drills → briefing → workspace → debrief before sign-off. The NVDA pass starts in phase 4 (§14.5).

## 5. Route transitions

React `<ViewTransition>` on drills → track → briefing (`components/page-transition.tsx`). These navigations happen tens of times a day, so the effect is a 12 px shift plus a fade on the 150/200 ms tokens. It runs only on links that declare a direction; browser back/forward and untyped navigations swap instantly. The token durations are 0 ms under reduced motion.

## 6. "Not LeetCode" review (owner sign-off required)

Automated captures of LeetCode and HackerRank were blocked: LeetCode returns a Cloudflare "Just a moment…" challenge and HackerRank returns "Access Denied". The side-by-side therefore has to be done by the owner. Open `docs/design/qc/phase-1/drills--dark--1440.jpg`, `incident_inc-4021--dark--1440.jpg` and `home--light--1440.jpg` next to leetcode.com/problemset, hackerrank.com and any indigo SaaS dashboard.

What to compare:

| Trait | LeetCode / HackerRank / indigo SaaS | DevGrill |
|---|---|---|
| Neutrals | Cool charcoal (LC), near-black + glow (SaaS) | Warm graphite (H75); paper off-white in light mode |
| Accent | Orange (LC), green (HR), indigo/violet (SaaS) | Signal cyan, which collides with no semantic colour |
| Difficulty or severity | Easy/Medium/Hard as green/amber/red text | SEV1–4 glyph ladder + label + colour |
| Headlines | Sans everywhere | Instrument Serif "field manual" headlines on briefings and debriefs |
| Core screen | Problem statement + code editor | Live system: charts, terminal, war room, incident timeline |
| Progress | Solved-count tables | System map with mastery rings, ratings per track |

**Sign-off:** ☐ Owner confirms DevGrill reads as its own brand (date: ____).
