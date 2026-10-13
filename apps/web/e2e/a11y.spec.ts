import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Every template, both themes, WCAG 2.2 AA (docs/PLAN.md §8.7). Pages that need an account
 * (settings, profiles, admin) are audited signed in, in a11y-signed-in.spec.ts.
 */
const ROUTES = [
  "/",
  "/sign-in",
  "/status",
  "/drills",
  "/drills/caching",
  "/drills/caching/big-sale-meltdown",
  "/daily",
  "/incident/inc-4021",
  "/incident/inc-4021/debrief",
  "/incident/inc-4021/postmortem",
  "/quickfire",
  "/this-page-does-not-exist",
];

for (const theme of ["light", "dark"] as const) {
  test.describe(`${theme} theme`, () => {
    test.use({ colorScheme: theme });

    for (const route of ROUTES) {
      test(`${route} has no WCAG 2.2 AA violations`, async ({ page }) => {
        await page.addInitScript((t) => localStorage.setItem("devgrill-theme", t), theme);
        await page.goto(route);
        await page.evaluate(() => document.fonts.ready);
        await expect(page.locator("html")).toHaveClass(new RegExp(theme));
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
          // Next.js dev overlay (dev server only) is not part of the product.
          .exclude("nextjs-portal")
          .analyze();
        const summary = results.violations.map(
          (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
        );
        expect(summary, summary.join("\n")).toEqual([]);
      });
    }
  });
}
