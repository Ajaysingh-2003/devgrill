// Fail if player-facing text uses DevGrill's internal words instead of the plain ones
// (docs/design/voice.md). Usage: node scripts/check-copy.mjs
// Parses with the repo's own TypeScript (no extra dependency): JSX text and prose-like string
// literals are checked; class names, routes, imports, keys, types and comments are not.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import ts from "typescript";

const ROOTS = ["apps/web/app/", "apps/web/components/", "packages/ui/src/components/devgrill/"];
// Admin pages are for us: internal names are fine there.
const EXCLUDED = ["apps/web/app/admin/", "apps/web/components/admin/"];
const EXTENSIONS = /\.tsx?$/;
const SKIP_FILES = /\.(stories|test)\.tsx?$/;

// The "Don't say" column of docs/design/voice.md.
const BANNED =
  /\b(sandbox(?:es)?|attempts?|probes?|SLOs?|telemetry|debrief|postmortem|war room|approach(?:es)?)\b/i;
// Attributes whose values are never read by players.
const NON_PROSE_ATTRIBUTES = new Set([
  "className",
  "href",
  "src",
  "id",
  "key",
  "role",
  "type",
  "name",
  "htmlFor",
  "value",
  "method",
  "action",
  "rel",
  "target",
  "aria-controls",
  "aria-labelledby",
  "aria-describedby",
]);
// Calls that build class lists or keys, not sentences.
const NON_PROSE_CALLS = new Set(["cn", "cva", "clsx", "twMerge", "require", "useHotkey", "addEventListener"]);

const files = execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard"], {
  encoding: "utf8",
})
  .split("\n")
  .filter(
    (f) =>
      ROOTS.some((r) => f.startsWith(r)) &&
      !EXCLUDED.some((r) => f.startsWith(r)) &&
      EXTENSIONS.test(f) &&
      !SKIP_FILES.test(f) &&
      existsSync(f),
  );

function isProse(text) {
  const t = text.trim();
  if (!t.includes(" ")) return false; // identifiers, keys, single tokens
  if (t.startsWith("/") || t.includes("://") || t.includes("/incident/")) return false; // routes
  return true;
}

function skippedByParent(node) {
  const parent = node.parent;
  if (!parent) return false;
  if (ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent)) return true;
  if (ts.isLiteralTypeNode(parent)) return true;
  if (ts.isPropertyAssignment(parent) && parent.name === node) return true;
  if (ts.isJsxAttribute(parent) && NON_PROSE_ATTRIBUTES.has(parent.name.getText())) return true;
  if (
    ts.isJsxExpression(parent) &&
    ts.isJsxAttribute(parent.parent) &&
    NON_PROSE_ATTRIBUTES.has(parent.parent.name.getText())
  )
    return true;
  // Inside a class-list or key-building call, at any depth of arguments.
  for (let p = parent; p; p = p.parent) {
    if (ts.isCallExpression(p) && NON_PROSE_CALLS.has(p.expression.getText())) return true;
    if (ts.isJsxAttribute(p) && p.name.getText() === "className") return true;
    if (ts.isBlock(p) || ts.isSourceFile(p)) break;
  }
  return false;
}

const problems = [];
for (const file of files) {
  const source = readFileSync(file, "utf8");
  const lines = source.split("\n");
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  // JSX text is always read by players; a string literal only when it looks like prose.
  const check = (node, text, jsx = false) => {
    const match = text.match(BANNED);
    if (!match || (!jsx && !isProse(text))) return;
    const { line } = sf.getLineAndCharacterOfPosition(node.getStart(sf));
    if (lines[line]?.includes("copy-ok")) return; // explicit, reviewed escape hatch
    problems.push(`${file}:${line + 1}  "${match[0]}" in: ${text.trim().replace(/\s+/g, " ").slice(0, 90)}`);
  };
  const visit = (node) => {
    if (ts.isJsxText(node)) {
      check(node, node.getText(sf), true);
    } else if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      if (!skippedByParent(node)) check(node, node.text);
    } else if (ts.isTemplateExpression(node)) {
      if (!skippedByParent(node)) {
        const text = [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join(" … ");
        check(node, text);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
}

if (problems.length) {
  console.error("Player-facing text uses internal words. See docs/design/voice.md for the plain ones:");
  for (const p of problems) console.error(`  ${p}`);
  console.error(`${problems.length} to fix (or mark a reviewed exception with // copy-ok).`);
  process.exit(1);
}
console.log(`copy: ${files.length} player-facing files use plain words`);
