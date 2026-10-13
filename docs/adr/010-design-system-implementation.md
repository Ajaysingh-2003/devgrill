# 010. Design system implementation choices

Date: 2026-10-13 · Status: accepted

## Context
Phase 1 built the token pipeline, the component library and the page templates. Several implementation choices differ from the plan (§7, Phase 1 tasks), or weren't specified there, and later phases depend on them.

## Decision
1. **Tokens are generated, not committed.**
   - `packages/tokens/tokens.json` is the only source. `src/build.ts` writes `dist/tokens.css` (variables per theme), `dist/theme.css` (the Tailwind `@theme inline` bridge, with the default palette removed), `dist/tokens.ts` (typed values for canvas and JS) and `dist/contrast.json`.
   - The build exits non-zero if any declared text/background pair misses its WCAG target in either theme, so the contrast check needs no separate test.
   - Turbo runs it before anything that depends on it (`^build`).
2. **Own `ThemeProvider` instead of `next-themes`.**
   - It is about 130 lines on `useSyncExternalStore` (SSR-safe, no set-state-in-effect).
   - It stores theme and motion preferences, syncs `<html class>`, `data-motion` and `<meta name="theme-color">`, and ships an inline no-flash script.
   - `next-themes` covers only the theme half and would still need the motion half built alongside it.
3. **Reduced motion has two sources.**
   - The sources are the OS setting and the in-app setting (`system | reduce | full`).
   - CSS reads them through the duration tokens, which become 0 ms.
   - `motion/react` reads them through `<MotionPreferences>` (`MotionConfig`), and components use `useReducedMotionConfig()`.
   - `MotionPreferences` lives in the route-group layouts that animate, so the landing page doesn't ship the motion library.
4. **shadcn components are fetched by script.**
   - `packages/ui/scripts/fetch-shadcn.ts` pulls the base-nova (Base UI) sources from the public registry.
   - It rewrites the imports and maps shadcn's theme classes to DevGrill tokens.
   - `shadcn add` can't run here: its package-manager step goes through the blocked `cmd.exe` (ADR 009), and its alias rewriting broke imports.
   - We own the copied code afterwards, as shadcn intends.
5. **Prettier 3 with the Tailwind plugin** for TS, CSS, JSON and Markdown (ESLint stays for correctness, ADR 008). It is checked in CI.
6. **Raw colours are guarded** by `scripts/check-raw-colors.mjs` (CI). It rejects hex, `rgb()`, `oklch()` and palette classes in UI code. `// raw-color-ok` is the escape hatch.
7. **Component tests run in a real browser.**
   - Storybook stories run through `@storybook/addon-vitest` in Chromium (Playwright), with axe as a failing check.
   - There are two configurations: light with full motion, and dark with in-app reduced motion.
   - Page-level checks (axe on every route in both themes, plus keyboard flows) run in Playwright against the production build.
8. **Route transitions use React 19.3 `<ViewTransition>`** (stable, no Next config).
   - They apply only to the drills hierarchy, with direction declared per link.
   - The workspace and debrief keep their own motion rules.

## Consequences
- Contributors must run `just tokens` (or any turbo task) after editing `tokens.json`; editors show stale types until they do.
- New shadcn components come from the fetch script and need a review of their mapped classes. Upstream updates are re-fetched, not merged.
- The theme provider is ours to maintain. It is covered by the e2e theme-persistence test and the Storybook theme matrix.
- CI needs Playwright Chromium in two jobs (`web` and `ui`), which adds about a minute each.
