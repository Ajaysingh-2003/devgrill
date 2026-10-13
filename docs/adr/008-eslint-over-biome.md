# 008. ESLint (Next.js config) for JS linting, not Biome

Date: 2026-10-13 · Status: accepted

## Context
Next.js 16.4's `create-next-app` scaffolds ESLint 9 with `eslint-config-next` (core-web-vitals + typescript). Biome 2.5 is faster but lacks the Next-specific rules (image, link, script, React hooks rules as configured by Next).

## Decision
Keep **ESLint 9 + eslint-config-next 16.4** for the web app. Formatting for TS/CSS is left to ESLint and editor defaults for now; Prettier is added in phase 1 together with the design-system code (Tailwind class sorting).

## Consequences
Lint runs through Turborepo (`pnpm lint`). If lint time becomes a problem, revisit Biome with the Next plugin rules it supports then.

## Alternatives considered
Biome 2.5 (speed; missing Next rules), oxlint (same gap).
