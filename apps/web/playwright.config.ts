import { defineConfig, devices } from "@playwright/test";
import { API_URL, IDP_URL, PYTHON, ROOT, STACK_ENV, WEB_PORT, WEB_URL } from "./e2e/stack.mjs";

/**
 * End-to-end: the production web build, the API and a mock GitHub, on their own ports and
 * database (e2e/stack.mjs). `pnpm e2e` rebuilds the database first (e2e/prepare-db.mjs).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // Each worker is a browser hitting one web server and one API: more workers than this just
  // queues requests and turns slow pages into flaky timeouts.
  workers: process.env.CI ? 2 : 4,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: [
    {
      command: "node e2e/mock-github.mjs",
      url: `${IDP_URL}/__mock/health`,
      env: STACK_ENV,
      reuseExistingServer: false,
    },
    {
      command: `"${PYTHON}" -m devgrill_api`,
      cwd: ROOT,
      url: `${API_URL}/healthz`,
      env: STACK_ENV,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // CI and `just e2e` run `next build` first.
      command: `node node_modules/next/dist/bin/next start --port ${WEB_PORT}`,
      url: WEB_URL,
      env: STACK_ENV,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
