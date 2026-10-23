# DevGrill design system

How the design system is built and how to use it when adding UI. The *why* (direction, palette rationale, type choices) lives in `docs/PLAN.md` §7–8; this file is the working reference.

## Where things live

| What | Where |
|---|---|
| Token source of truth | `packages/tokens/tokens.json` |
| Token generator + contrast gate | `packages/tokens/src/build.ts` → `dist/` (generated, git-ignored) |
| Tailwind bridge | `dist/theme.css` (`@theme inline`; the default Tailwind palette is removed) |
| Base layer (focus ring, reduced motion, heading balance, tabular numbers) | `packages/ui/src/styles/base.css` |
| shadcn primitives (Base UI) | `packages/ui/src/components/ui/` (fetched by `packages/ui/scripts/fetch-shadcn.ts`, never hand-edited for tokens) |
| DevGrill components | `packages/ui/src/components/devgrill/` |
| Theme + motion preference | `packages/ui/src/theme/` (`ThemeProvider`, `MotionPreferences`, no-flash `themeInitScript`) |
| Motion presets for `motion/react` | `packages/ui/src/motion/index.ts` |
| Icons, wordmark, SEV glyphs | `packages/ui/src/icons/index.tsx` |
| Fonts | `apps/web/app/fonts.ts` |
| Stories | `*.stories.tsx` next to the components |

## Tokens

**Never write a raw colour.** `pnpm colors:check` fails on hex, `rgb()`, `oklch()` and Tailwind palette classes in `apps/web` and `packages/ui`. The single escape hatch is a `// raw-color-ok` comment on the line, and the OG image is exempt because it renders outside the CSS.

Semantic colour utilities (every one exists in light and dark):

| Role | Utilities |
|---|---|
| Surfaces | `bg-canvas` (page), `bg-surface` (cards, panels), `bg-raised` (hover, selected), `bg-sunken` (code, terminal) |
| Text | `text-fg`, `text-fg-muted`, `text-fg-subtle`, `text-fg-inverse` |
| Lines | `border-border`, `border-border-strong`, `border-border-input` |
| Brand (Signal cyan) | `bg-brand` + `text-on-brand`, `hover:bg-brand-hover`, `text-brand-text` (links on surfaces), `bg-brand-subtle` |
| Status | `{danger,warning,success,info}-text` / `-subtle` / `-solid`, with `text-on-danger` and `text-on-success` |
| Severity | `sev1`–`sev4` `-fg` / `-bg` (use `<SevBadge>`, which adds the glyph and label) |
| Arcade only | `flare`, `volt` (+ `on-*`). Never inside the incident workspace |
| Charts | `chart-1`–`chart-8`, `chart-threshold`, `chart-breach` (read at runtime by `MetricChart`) |
| Focus | `ring-focus-ring` (the base layer already outlines `:focus-visible`) |

**Contrast is a build failure.** `tokens.json` declares every text/background pair with its target (4.5:1 text, 3:1 UI marks). `pnpm --filter @devgrill/tokens build` exits non-zero if any pair misses in either theme. Currently 104/104 pairs pass. Adding a token means adding its pairs.

Other scales: radius `rounded-xs/sm/md/lg/full` (4/6/10/14), z-index `z-[var(--z-*)]` (sticky → toast), shadows `shadow-float` (floating layers only; borders do the rest).

## Typography

| Utility | Face | Use |
|---|---|---|
| `font-sans` (default) | Instrument Sans | All UI and long-form text, including form inputs |
| `font-serif` | Instrument Serif | Field Manual **headlines only** (briefing, debrief, postmortem titles). Never body text or inputs, and never inside the workspace |
| `font-mono` | JetBrains Mono | Terminal, logs, IDs, timestamps, metrics |
| `font-display` | Bricolage Grotesque, falling back to the UI face | Arcade layer: landing hero, streaks, Quick Fire. The `--font-arcade` variable is only set by the marketing, app and quickfire layouts, so other routes don't download it |

Type scale utilities: `text-display-{2xl,xl,lg}`, `text-heading-{lg,md}`, `text-body-lg`, `text-body`, `text-label`, `text-caption`, `text-mono`, `text-mono-sm`, `text-stat`. Numbers that update use `tabular-nums` (automatic inside `time`, `kbd`, `code`, `pre` and `samp`). Headings balance automatically (`text-wrap: balance` in the base layer). Sentence case everywhere.

## Theme and motion preferences

- `ThemeProvider` (root layout) stores `devgrill-theme` (`system | light | dark`) and `devgrill-motion` (`system | reduce | full`) in localStorage and keeps `<html class>`, `data-motion` and `<meta name="theme-color">` in sync. `themeInitScript` applies them before first paint, so there is no flash.
- Read them with `useTheme()` → `{ theme, resolvedTheme, motion, reducedMotion, setTheme, setMotion }`.
- Wrap animated routes in `<MotionPreferences>`. It feeds `reducedMotion` into motion's `MotionConfig`. In components, read it with **`useReducedMotionConfig()`** from `motion/react`, never `useReducedMotion()`: that reads only the OS setting and ignores the in-app choice.
- CSS durations are tokens (`--duration-fast` 120 ms, `--duration-base-in` 200 ms, `--duration-base-out` 150 ms, `--duration-slow` 320 ms, `--duration-celebrate` 800 ms). They become 0 ms when the OS asks for reduced motion (unless the user picked "Full motion") or when the user picked "Reduce motion". Use them, `--ease-standard`, `--ease-enter` and `--ease-exit` (all ease-out shapes) for every transition.

## Motion rules

1. **Keyboard-initiated changes are instant**: the palette, focus mode and tool switching.
2. **Streaming surfaces never animate**: logs, terminal output, charts (data snaps) and the incident timeline.
3. **One celebration**: `VerifyCelebration` on the debrief (~950 ms). It can be skipped with any key or click, jumps to the end under reduced motion, and is never reused on frequent surfaces.
4. **Route transitions** (drills → track → briefing) use React `<ViewTransition>` through `apps/web/components/page-transition.tsx`. Links opt in with `transitionTypes={["nav-forward"]}` or `["nav-back"]`. The effect is a 12 px shift plus a fade on token durations.
5. Animate only `transform`, `opacity` and `clip-path`; never `transition: all`; never `scale(0)`. Gate hover motion behind `(hover: hover)`.

## Accessibility patterns to reuse

- **Landmarks:** the root layout renders the skip link, so every template must have exactly one `<main id="main">` (e2e checks five templates).
- **Panels:** `PanelFrame` gives a real heading plus a focusable, labelled scroll region. Pass `tab="tool-x"` when a tablist controls it; it then renders as that tab's `tabpanel`.
- **Tool rail:** a vertical ARIA tablist (roving tabindex, ↑/↓/Home/End). Number keys 1–6 switch tools except while typing (`isTypingTarget`).
- **Splitters:** react-resizable-panels separators (WAI-ARIA window splitter: arrow keys resize). Collapsed panels get `inert`, so Tab never lands at 0 px width.
- **Toggles:** a set of mutually exclusive buttons is a `role="group"` with `aria-pressed`. Use `role="radio"` only with a real radio implementation (Base UI `RadioGroup`, as in `ApproachList` and `ModePicker`).
- **Status never by colour alone:** severity = glyph + label + colour; probe results = icon + text; Quick Fire answers = icon + "Correct" / "Your pick".
- **Announcements:** one `role="alert"` per workspace (genuine pages only), filled after mount so it is announced. Everything else stays quiet: no `aria-live` on content that changes as the user navigates.
- **Hotkeys:** `useHotkey("mod+k", …)` handles platform modifiers. Any shortcut shown in the palette must be bound.

## Adding a component

1. Start from a shadcn primitive if one exists. Run `node packages/ui/scripts/fetch-shadcn.ts <name>`; it maps shadcn tokens to ours.
2. Put it in `components/devgrill/`, using semantic tokens and CVA for variants.
3. Write a story covering every state. Its `play()` should exercise any interaction.
4. Run `just test-web`. Every story renders twice in Chromium, light with full motion and dark with in-app reduced motion, and each render must pass an axe audit (`a11y.test: "error"`).
5. If it ships on a page, `just e2e` audits every route in both themes.

## Commands

| Command | What it does |
|---|---|
| `just tokens` | Regenerate tokens; fails on any contrast miss |
| `just storybook` | Storybook on :6006 with theme and motion toolbars |
| `just test-web` | Token tests, UI unit tests, all stories × 2 configurations with axe |
| `just e2e` | Production build, then axe on 15 routes × 2 themes plus keyboard and motion flows |
| `just colors-check` / `just fmt-web` | Raw-colour guard / Prettier (with Tailwind class sorting) |
| `just shots <dir> <paths…>` | Screenshot matrix (light/dark × 1440/1024/390) of a running app |
