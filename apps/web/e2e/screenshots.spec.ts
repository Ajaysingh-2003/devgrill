import { expect, test } from "@playwright/test";
import { signIn, sql, uniqueLogin } from "./helpers";

/**
 * Design QC evidence (docs/PLAN.md §14.5): the pages that show real data, signed in with some
 * progress, light/dark at 1440 and 390. Only with SCREENSHOTS=1:
 *   SCREENSHOTS=1 pnpm --filter @devgrill/web exec playwright test e2e/screenshots.spec.ts
 */
const OUT = "../../docs/design/qc/phase-2";

test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to capture QC screenshots");

test("phase 2 pages with real data", async ({ page }) => {
  test.setTimeout(180_000);
  const login = uniqueLogin("qc");
  await signIn(page, login);
  // Some history: one solved, one attempted, a three-day streak.
  await sql(
    `WITH me AS (SELECT user_id FROM app.profiles WHERE handle = $1)
     INSERT INTO app.attempts (user_id, scenario_version_id, mode, state, started_at, resolved_at, ended_at)
     SELECT me.user_id, s.current_version_id, 'guided', st.state::app.attempt_state,
            now() - interval '2 days', now() - interval '2 days' + interval '14 minutes', now()
     FROM me, app.scenarios s
     JOIN (VALUES ('ttl-zero', 'resolved'), ('pool-party', 'abandoned')) AS st(slug, state)
       ON st.slug = s.slug`,
    [login],
  );
  await sql(
    `INSERT INTO app.activity_days (user_id, day)
     SELECT user_id, (now() AT TIME ZONE 'Asia/Kolkata')::date - d
     FROM app.profiles, generate_series(0, 2) d WHERE handle = $1`,
    [login],
  );

  const pages = [
    ["drills", "/drills"],
    ["track", "/drills/caching"],
    ["briefing", "/drills/caching/big-sale-meltdown"],
    ["profile", `/u/${login}`],
    ["settings", "/settings"],
  ] as const;
  for (const theme of ["light", "dark"] as const) {
    // Signed in, the profile's theme wins over this device's (PrefsSync), so set it there.
    await sql(
      `UPDATE app.profiles SET prefs = prefs || jsonb_build_object('theme', $2::text) WHERE handle = $1`,
      [login, theme],
    );
    await page.evaluate((t) => localStorage.setItem("devgrill-theme", t), theme);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width < 600 ? 844 : 900 });
      for (const [name, url] of pages) {
        await page.goto(url);
        await page.waitForLoadState("networkidle");
        await expect(page.locator("html")).toHaveClass(new RegExp(theme));
        await page.screenshot({ path: `${OUT}/${name}--${theme}--${width}.jpg`, type: "jpeg", quality: 72 });
      }
    }
  }
});
