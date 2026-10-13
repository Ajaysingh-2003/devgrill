# Vendored skills

These Claude Code skills are copied into the repo so every session (and every contributor)
builds the UI against the same design, accessibility and motion rules. They were reviewed
before vendoring: markdown only, no install scripts, no runtime network fetches.

Copied on 2026-10-12. To update a skill, re-clone its repo, diff against the folder here,
review the diff, and update the commit in this table.

| Skill folder | Upstream repo | Path in repo | Commit | License |
|---|---|---|---|---|
| frontend-design | https://github.com/anthropics/skills | skills/frontend-design | dbd4588 | Apache-2.0 (LICENSE.txt) |
| tailwind-design-system | https://github.com/wshobson/agents | plugins/frontend-mobile-development/skills/tailwind-design-system | 46891e7 | MIT |
| oklch-skill | https://github.com/jakubkrehel/oklch-skill | skills/oklch-skill | 0e81f04 | MIT |
| web-design-guidelines | https://github.com/vercel-labs/agent-skills + https://github.com/vercel-labs/web-interface-guidelines | skills/web-design-guidelines + command.md | 063bee9 / 434b7f9 | MIT |
| accessibility | https://github.com/addyosmani/web-quality-skills | skills/accessibility | afa8da9 | MIT |
| core-web-vitals | https://github.com/addyosmani/web-quality-skills | skills/core-web-vitals | afa8da9 | MIT |
| emil-design-eng | https://github.com/emilkowalski/skills | skills/emil-design-eng | 2d22863 | MIT |
| animate | https://github.com/emilkowalski/skills | skills/animate | 2d22863 | MIT |
| review-animations | https://github.com/emilkowalski/skills | skills/review-animations | 2d22863 | MIT |
| animation-performance | https://github.com/emilkowalski/skills | skills/animation-performance | 2d22863 | MIT |
| apple-design | https://github.com/emilkowalski/skills | skills/apple-design | 2d22863 | MIT |
| vercel-react-best-practices | https://github.com/vercel-labs/agent-skills | skills/react-best-practices | 063bee9 | MIT (declared in upstream README and skill metadata; no LICENSE file upstream) |
| vercel-composition-patterns | https://github.com/vercel-labs/agent-skills | skills/composition-patterns | 063bee9 | MIT (as above) |
| vercel-react-view-transitions | https://github.com/vercel-labs/agent-skills | skills/react-view-transitions | 063bee9 | MIT (as above) |

## Local modifications

- `web-design-guidelines/SKILL.md`: replaced the per-run WebFetch of
  `raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` with the vendored
  copy `web-design-guidelines/guidelines.md`, so the skill's instructions can't change underneath us.

## Considered and not vendored

- `impeccable` (pbakaus/impeccable): strong, but its setup downloads and runs a native binary and can
  install hooks. Keep it as a personal global skill if wanted.
- `ui-ux-pro-max`, `taste-skill` variants, `ibelick/ui-skills`: redundant with the set above or
  conflicting with the motion rules (baseline-ui forbids custom easing).
