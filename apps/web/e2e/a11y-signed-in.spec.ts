import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signIn, uniqueLogin } from "./helpers";
import { ADMIN_LOGIN } from "./stack.mjs";

/** Pages that need an account, audited signed in (both themes, WCAG 2.2 AA). */
for (const theme of ["light", "dark"] as const) {
  test(`signed-in pages have no WCAG 2.2 AA violations (${theme})`, async ({ page }) => {
    test.slow();
    await page.addInitScript((t) => localStorage.setItem("devgrill-theme", t), theme);
    const login = uniqueLogin(`a11y-${theme}`);
    await signIn(page, login);
    for (const route of [
      "/drills",
      "/drills/caching",
      "/drills/caching/big-sale-meltdown",
      "/settings",
      `/u/${login}`,
    ]) {
      await page.goto(route);
      await page.evaluate(() => document.fonts.ready);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const summary = results.violations.map(
        (v) => `${route} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
      );
      expect(summary, summary.join("\n")).toEqual([]);
    }
  });
}

test("the admin console has no WCAG 2.2 AA violations", async ({ page }) => {
  await signIn(page, ADMIN_LOGIN);
  await page.goto("/admin");
  await expect(page.getByRole("table", { name: /Scenarios with status/ })).toBeVisible();
  await expect(page.getByRole("table", { name: /Model calls in the last 7 days/ })).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations.map((v) => v.id)).toEqual([]);
});
