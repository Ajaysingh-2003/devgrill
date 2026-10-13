// Fail if UI code uses raw colour values instead of semantic tokens (docs/PLAN.md phase 1 gate).
// Usage: node scripts/check-raw-colors.mjs
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

const ROOTS = ["apps/web/", "packages/ui/"];
const EXTENSIONS = /\.(tsx?|css|mjs)$/;
// Documented exceptions: OG images render outside the browser (no CSS variables), stories use tokens only.
const ALLOWED_FILES = new Set(["apps/web/app/opengraph-image.tsx"]);

const PALETTE =
  "black|white|slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const RULES = [
  { name: "hex colour", re: /(?<![\w&])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/g },
  { name: "rgb()/hsl() colour", re: /\b(?:rgba?|hsla?)\(/g },
  // Relative colours derived from a token (oklch(from var(--brand) …)) are allowed.
  { name: "raw oklch()", re: /\boklch\((?!\s*from\s+var\(--)/g },
  {
    name: "Tailwind palette class",
    re: new RegExp(
      `(?<![\\w-])(?:bg|text|border|ring|fill|stroke|outline|divide|from|via|to|decoration|placeholder|caret|accent|shadow)-(?:${PALETTE})(?:-\\d{2,3})?(?:\\/\\d+)?(?![\\w-])`,
      "g",
    ),
  },
];

const files = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard"], {
  encoding: "utf8",
})
  .split("\n")
  .filter(
    (f) => ROOTS.some((r) => f.startsWith(r)) && EXTENSIONS.test(f) && !ALLOWED_FILES.has(f) && existsSync(f),
  );

const problems = [];
for (const file of files) {
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    if (line.includes("raw-color-ok")) return; // explicit, reviewed escape hatch
    for (const rule of RULES) {
      for (const match of line.matchAll(rule.re)) {
        problems.push(`${file}:${i + 1}  ${rule.name}: ${match[0]}`);
      }
    }
  });
}

if (problems.length) {
  console.error("Raw colours found. Use semantic tokens (bg-surface, text-fg-muted, var(--brand) …):");
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}
console.log(`colors: ${files.length} UI files use semantic tokens only`);
