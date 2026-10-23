// Phase 4 soak: a long incident with the terminal busy and telemetry streaming. Records the
// tab's JS heap (after a forced GC) every minute.
// Gates: terminal 30-minute session, heap growth under 20%; telemetry 1-hour stream, no
// unbounded memory (sample and log ring buffers).
//
//   node e2e/soak.mjs [minutes=60] [baseUrl]
// Needs the dev stack with GitHub pointed at the mock IdP (e2e/mock-github.mjs on :3999).
import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const MINUTES = Number(process.argv[2] ?? 60);
const BASE = process.argv[3] ?? "http://localhost:3000";
const LOGIN = `soak-${Date.now().toString(36)}`;
const t0 = Date.now();
const log = (m) => console.log(`[${((Date.now() - t0) / 60000).toFixed(1)} min] ${m}`);

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
await context.addCookies([{ name: "mock_user", value: LOGIN, url: "http://localhost:3999" }]);
const page = await context.newPage();
const heap = [];
let ok = false;
try {
  await page.goto(`${BASE}/sign-in?next=/drills`);
  await page.waitForLoadState("networkidle");
  const button = page.getByRole("button", { name: /Continue with GitHub/ });
  for (let i = 0; i < 10 && new URL(page.url()).pathname === "/sign-in"; i++) {
    await button.click().catch(() => {});
    await page.waitForTimeout(2000);
  }
  await page.waitForURL((u) => u.pathname === "/drills", { timeout: 30_000 });
  // Pro: a 45-minute session with two 15-minute extensions covers the hour.
  const sql = `UPDATE app.entitlements e SET plan = 'pro' FROM app.profiles p WHERE p.user_id = e.user_id AND p.handle = '${LOGIN}'`;
  const res = spawnSync(
    "docker",
    ["exec", "devgrill-dev-postgres-1", "psql", "-U", "devgrill", "-d", "devgrill", "-c", sql],
    { encoding: "utf8" },
  );
  if (!res.stdout.includes("UPDATE 1"))
    throw new Error(`could not make ${LOGIN} pro: ${res.stdout}${res.stderr}`);
  log(`signed in as ${LOGIN} (pro)`);

  await page.goto(`${BASE}/drills/caching/big-sale-meltdown`);
  await page.getByRole("radio", { name: /No hints/ }).click();
  await page.getByRole("button", { name: "Start the drill" }).click();
  await page.waitForURL(/\/incident\/[0-9a-f-]{36}$/, { timeout: 60_000 });
  await page.getByText("oncall@shopkart: Connected").waitFor({ timeout: 180_000 });
  log(`active: ${page.url()}`);

  const cdp = await context.newCDPSession(page);
  await cdp.send("Performance.enable");
  const measure = async () => {
    await cdp.send("HeapProfiler.collectGarbage");
    const { metrics } = await cdp.send("Performance.getMetrics");
    const used = metrics.find((m) => m.name === "JSHeapUsedSize")?.value ?? 0;
    const nodes = metrics.find((m) => m.name === "Nodes")?.value ?? 0;
    // Elements per panel, to tell a leak from panels that legitimately grow (the timeline).
    const panels = await page.evaluate(() => {
      const out = { all: document.querySelectorAll("*").length };
      for (const s of document.querySelectorAll("section[id], aside")) {
        out[s.id || s.getAttribute("aria-label") || s.tagName] = s.querySelectorAll("*").length;
      }
      return out;
    });
    heap.push({
      minute: Math.round((Date.now() - t0) / 60000),
      mb: +(used / 1024 / 1024).toFixed(2),
      nodes,
      panels,
    });
    log(`heap ${heap.at(-1).mb} MB, ${nodes} DOM nodes ${JSON.stringify(panels)}`);
  };

  const term = page.locator(".xterm");
  const extendsAt = [38, 52];
  const end = Date.now() + MINUTES * 60_000;
  let nextHeap = Date.now();
  while (Date.now() < end) {
    await term.click();
    await page.keyboard.type("date; redis-cli -h redis-db INFO stats | head -5\n");
    if (Date.now() >= nextHeap) {
      await measure();
      nextHeap += 60_000;
    }
    const minute = (Date.now() - t0) / 60000;
    if (extendsAt.length && minute >= extendsAt[0]) {
      extendsAt.shift();
      await page.getByRole("heading", { level: 1 }).click();
      await page.keyboard.press("Control+k");
      await page.getByRole("combobox").fill("Extend by");
      await page.keyboard.press("Enter");
      log("extended the session");
    }
    await page.waitForTimeout(20_000);
  }
  await measure();
  ok = true;
} catch (err) {
  console.error(String(err));
  await page.screenshot({ path: "test-results/soak-failure.png" }).catch(() => {});
} finally {
  const at = (m) => heap.find((h) => h.minute >= m) ?? heap.at(-1);
  const base = at(5);
  const summary = {
    ok,
    login: LOGIN,
    samples: heap.length,
    base_mb: base?.mb,
    at_30_mb: at(30)?.mb,
    at_end_mb: heap.at(-1)?.mb,
    growth_30_pct: base && at(30) ? +(((at(30).mb - base.mb) / base.mb) * 100).toFixed(1) : null,
    growth_end_pct: base && heap.at(-1) ? +(((heap.at(-1).mb - base.mb) / base.mb) * 100).toFixed(1) : null,
    heap,
  };
  writeFileSync("test-results/soak.json", JSON.stringify(summary, null, 2));
  console.log(JSON.stringify({ ...summary, heap: undefined }, null, 2));
  await page
    .getByRole("heading", { level: 1 })
    .click()
    .catch(() => {});
  await page.keyboard.press("Control+k").catch(() => {});
  await page
    .getByRole("combobox")
    .fill("Leave the incident")
    .catch(() => {});
  await page.keyboard.press("Enter").catch(() => {});
  await page
    .getByRole("button", { name: "Leave", exact: true })
    .click()
    .catch(() => {});
  await page.waitForTimeout(3000);
  await browser.close();
  process.exit(ok ? 0 : 1);
}
