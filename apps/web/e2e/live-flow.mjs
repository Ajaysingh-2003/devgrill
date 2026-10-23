// The full loop on the real stack (web, API, worker, gateway, Temporal, Docker), as a guest
// playing ttl-zero: start -> terminal (and a reload) -> the in-sandbox CLI -> logs and metrics
// -> roll back -> mitigated -> fix the config in the editor and deploy -> verify (phase 5) ->
// debrief -> postmortem. Also measures keystroke echo latency through the gateway (gate: p95 <
// 80 ms), sample-to-chart delay (gate: < 2.5 s) and how long verify takes (gate: < 4 min).
//
//   node e2e/live-flow.mjs [baseUrl]      (run the stack first: `just dev`)
import { chromium } from "@playwright/test";

const BASE = process.argv[2] ?? "http://localhost:3000";
const results = {};
const t0 = Date.now();
const step = (name) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${name}`);

const browser = await chromium.launch();
// RECORD=1 saves a video of the whole run (the M1 demo capture) to test-results/video/.
const viewport = { width: 1600, height: 1000 };
const context = await browser.newContext({
  viewport,
  ...(process.env.RECORD ? { recordVideo: { dir: "test-results/video", size: viewport } } : {}),
});
const page = await context.newPage();
// Time every terminal keystroke frame and the next screen frame after it.
await page.addInitScript(() => {
  const w = window;
  w.__echo = [];
  w.__samples = [];
  const NativeWS = window.WebSocket;
  class Probe extends NativeWS {
    constructor(url, protocols) {
      super(url, protocols);
      const terminal = String(url).includes("/terminal");
      const telemetry = String(url).includes("/telemetry");
      this.addEventListener("message", (e) => {
        if (terminal && typeof e.data !== "string" && w.__pending !== undefined) {
          w.__echo.push(performance.now() - w.__pending);
          w.__pending = undefined;
        }
        if (telemetry && typeof e.data === "string" && e.data.includes('"type": "sample"')) {
          const frame = JSON.parse(e.data);
          w.__samples.push(Date.now() / 1000 - frame.t);
        }
      });
      if (terminal) {
        const send = this.send.bind(this);
        this.send = (data) => {
          if (typeof data !== "string") w.__pending = performance.now();
          send(data);
        };
      }
    }
  }
  window.WebSocket = Probe;
});

try {
  await page.goto(`${BASE}/drills/caching/ttl-zero`);
  await page.getByRole("button", { name: "Start the drill" }).click();
  await page.waitForURL(/\/incident\/[0-9a-f-]{36}$/, { timeout: 60_000 });
  const started = Date.now();
  step(`started ${page.url()}`);

  await page.getByText("Getting your drill ready").waitFor({ timeout: 30_000 });
  await page.getByText("Getting your drill ready").waitFor({ state: "detached", timeout: 180_000 });
  results.time_to_active_ui_s = (Date.now() - started) / 1000;
  step("active");

  await page.getByText("oncall@shopkart: Connected").waitFor({ timeout: 60_000 });
  const term = page.locator(".xterm");
  await term.click();
  await page.waitForTimeout(500);
  for (const ch of "echo keystroke-latency-probe") {
    await page.keyboard.type(ch);
    await page.waitForTimeout(120);
  }
  await page.keyboard.press("Enter");
  await page.keyboard.type("git log --oneline | head -4\n");
  await page.getByText("ops: tune cache TTL").first().waitFor({ timeout: 20_000 });
  const echo = (await page.evaluate(() => window.__echo)).sort((a, b) => a - b);
  results.echo_ms = {
    n: echo.length,
    p50: Math.round(echo[Math.floor(echo.length / 2)]),
    p95: Math.round(echo[Math.floor(echo.length * 0.95)]),
  };
  step(`terminal ok, echo ${JSON.stringify(results.echo_ms)}`);

  await page.keyboard.type("devgrill status\n");
  await page.getByText("postgres-db").first().waitFor({ timeout: 30_000 });
  step("in-sandbox CLI ok");

  // A reload re-attaches to the same tmux session: the earlier output is still on screen.
  await page.reload();
  await page.getByText("oncall@shopkart: Connected").waitFor({ timeout: 60_000 });
  await page.locator(".xterm").getByText("keystroke-latency-probe").first().waitFor({ timeout: 20_000 });
  results.terminal_survives_reload = true;
  step("terminal survived a reload");

  await page.getByRole("tab", { name: "Logs" }).click();
  await page.getByRole("log", { name: "Log lines" }).locator("button").first().waitFor({ timeout: 60_000 });
  step("logs ok");

  await page.getByRole("tab", { name: /Overview/ }).click();
  await page.locator("figure").first().waitFor({ timeout: 30_000 });
  await page.waitForTimeout(6000);
  const lags = await page.evaluate(() => window.__samples);
  results.sample_to_browser_s = lags.length ? Math.max(...lags).toFixed(2) : null;
  step(`charts ok, sample lag max ${results.sample_to_browser_s}s`);

  // Roll back the config deploy that set the TTL to 0.
  await page.getByRole("tab", { name: "Deploys" }).click();
  const target = page.getByRole("listitem").filter({ hasText: "product page: show stock badge" });
  await target.getByRole("button", { name: /Roll back to/ }).click();
  await target.getByRole("button", { name: /now$/ }).click();
  await page
    .getByText(/is live/)
    .first()
    .waitFor({ timeout: 120_000 });
  step("rolled back");

  await page.getByRole("tab", { name: "Timeline" }).click();
  await page.getByText("Working again: back under target").waitFor({ timeout: 180_000 });
  results.mitigated_after_rollback = true;
  step("mitigated");

  // Fix forward in the editor: the rollback deployed an older commit, but the working tree still
  // has TTL=0, so the next deploy must carry a real TTL. The app keeps the first value it reads.
  await page.getByRole("tab", { name: "Code" }).click();
  await page.getByRole("button", { name: "config/app.env" }).click();
  const editor = page.locator(".cm-content");
  await editor.waitFor({ timeout: 30_000 });
  await editor.click();
  await page.keyboard.press("Control+Home");
  await page.keyboard.type("CACHE_TTL_SECONDS=300\n");
  await page.keyboard.press("Control+Enter");
  await page
    .getByText(/api [0-9a-f]+ .*is live/)
    .first()
    .waitFor({ timeout: 120_000 });
  step("edited and deployed");
  await page.screenshot({ path: "test-results/live-flow.png" });

  // Verify (phase 5): progress probe by probe, then the verdict.
  const verifyStarted = Date.now();
  await page.getByRole("button", { name: "Check my fix", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByText(/Checking|checks done/)
    .first()
    .waitFor({ timeout: 60_000 });
  await dialog.getByRole("heading", { name: "Your fix works" }).waitFor({ timeout: 300_000 });
  results.verify_s = Math.round((Date.now() - verifyStarted) / 1000);
  step(`verify passed in ${results.verify_s}s`);

  await dialog.getByRole("link", { name: "See your results" }).click();
  await page.waitForURL(/\/debrief$/, { timeout: 60_000 });
  await page.getByRole("heading", { level: 1, name: "Your fix held up" }).waitFor();
  await page.getByText("Scoring your run…").waitFor({ state: "detached", timeout: 90_000 });
  await page.getByRole("table", { name: "The checks your fix faced, and how it did" }).waitFor();
  await page.getByRole("radio", { name: /Restore a positive TTL/ }).waitFor(); // approaches open
  results.debrief = true;
  step("debrief");
  await page.screenshot({ path: "test-results/debrief.png", fullPage: true });

  await page.getByRole("link", { name: "Write it up" }).click();
  await page.waitForURL(/\/postmortem$/, { timeout: 60_000 });
  await page
    .getByLabel("Summary")
    .fill("Product reads went to Postgres: an ops deploy set the cache TTL to 0.");
  await page.getByLabel("Root cause").fill("CACHE_TTL_SECONDS=0 disables caching in the product API.");
  await page.getByText(/Draft saved at/).waitFor({ timeout: 30_000 });
  await page.getByRole("button", { name: "Submit for review" }).click();
  await page.getByText(/^Submitted\./).waitFor({ timeout: 30_000 });
  results.postmortem = true;
  step("postmortem submitted");
  results.ok = true;
} catch (err) {
  results.ok = false;
  results.error = String(err).slice(0, 2000);
  await page.screenshot({ path: "test-results/live-flow-failure.png" }).catch(() => {});
} finally {
  await context.close(); // flushes the video, if recording
  await browser.close();
}
console.log(JSON.stringify(results, null, 2));
process.exit(results.ok ? 0 : 1);
