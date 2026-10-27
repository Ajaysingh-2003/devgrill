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
  test.slow();
  await signIn(page, ADMIN_LOGIN);
  const pages: [string, RegExp][] = [
    ["/admin", /Scenarios with status/],
    ["/admin/analytics", /Per scenario/],
    ["/admin/ai", /Model calls in the last 7 days/],
    ["/admin/users?q=oc", /Users matching/],
    ["/admin/audit", /Admin and content actions/],
  ];
  for (const [route, table] of pages) {
    await page.goto(route);
    if (route !== "/admin/audit") await expect(page.getByRole("table", { name: table })).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations.map((v) => `${route} ${v.id}`)).toEqual([]);
  }
});

test("an admin retires and restores a scenario, and the audit log shows it", async ({ page }) => {
  test.slow();
  await signIn(page, ADMIN_LOGIN);
  await page.goto("/admin");
  const row = page.getByRole("row", { name: /ghost-reads/ });
  await row.getByRole("button", { name: "Retire: ghost-reads" }).click();
  await expect(row.getByText("retired", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "Restore: ghost-reads" }).click();
  await expect(row.getByText("published", { exact: true })).toBeVisible();
  await page.goto("/admin/audit");
  await expect(page.getByRole("rowheader", { name: "scenario.retire" }).first()).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "scenario.restore" }).first()).toBeVisible();
});

test("a plain account sees no console sections", async ({ page }) => {
  // A plain account: no console sections, and the page explains the role it needs.
  await signIn(page, uniqueLogin("nora"));
  await page.goto("/admin");
  await expect(page.getByText("The content console needs another role")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Console" })).toHaveCount(0);
});
