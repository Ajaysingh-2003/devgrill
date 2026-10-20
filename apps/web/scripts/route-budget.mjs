// Initial JavaScript of a route, gzipped, from the production build (`pnpm build` first).
// Counts Next's runtime (rootMainFiles) plus the route's entry chunks: what the browser must
// load before the page works. Also checks that heavy libraries stay out of those chunks
// (they must be lazy-loaded): PLAN phase 4 gate, workspace ≤ 450 KB gz.
//
//   node scripts/route-budget.mjs "/(incident)/incident/[attemptId]/page" 450 xterm codemirror uPlot
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import vm from "node:vm";

const [route = "/(incident)/incident/[attemptId]/page", budgetKb = "450", ...lazy] = process.argv.slice(2);
const next = join(process.cwd(), ".next");

const build = JSON.parse(readFileSync(join(next, "build-manifest.json"), "utf8"));
const manifestFile = join(next, "server", "app", `${route.replace(/^\//, "")}_client-reference-manifest.js`);
const sandbox = { self: {}, globalThis: {} };
vm.runInNewContext(readFileSync(manifestFile, "utf8"), sandbox);
const rsc = sandbox.globalThis.__RSC_MANIFEST ?? sandbox.self.__RSC_MANIFEST;
const entry = rsc[route].entryJSFiles[`[project]/apps/web/app${route}`] ?? [];

const files = [...new Set([...(build.rootMainFiles ?? []), ...entry])];
let total = 0;
const found = new Set();
for (const file of files) {
  const source = readFileSync(join(next, file));
  const gz = gzipSync(source).length;
  total += gz;
  const text = source.toString("utf8");
  for (const name of lazy) if (text.includes(name)) found.add(name);
  console.log(`${(gz / 1024).toFixed(1).padStart(7)} KB  ${file}`);
}
const kb = total / 1024;
console.log(`${kb.toFixed(1).padStart(7)} KB  total (gzip), budget ${budgetKb} KB`);
let ok = kb <= Number(budgetKb);
if (found.size) {
  console.log(`not lazy: ${[...found].join(", ")} are in the initial chunks`);
  ok = false;
}
process.exit(ok ? 0 : 1);
