import { expect, test } from "@playwright/test";

/** Case files (ADR 018): a guest reads a recording and answers, with no sandbox and no sign-in. */
const SLUG = "pool-party";

test.describe("a case file", () => {
  test("is listed for anyone and links to its recording", async ({ page }) => {
    await page.goto("/case-files");
    await expect(page.getByRole("heading", { level: 1, name: "Case files" })).toBeVisible();
    await page.getByRole("link", { name: /Pool party/ }).click();
    await expect(page).toHaveURL(new RegExp(`/case-files/${SLUG}$`));
    await expect(page.getByRole("heading", { level: 1, name: "Pool party" })).toBeVisible();
  });

  test("shows the panels read-only, fed from the recording", async ({ page }) => {
    await page.goto(`/case-files/${SLUG}`);
    await expect(page.getByText("Recorded from a real run")).toBeVisible();

    // Overview draws the recorded series, with its target.
    await expect(page.getByText(/over target|Every target met|On target/)).toBeVisible();

    // Number keys switch panels, as in a live incident.
    await page.keyboard.press("2");
    await expect(page.getByRole("heading", { name: "Logs" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Freeze/ })).toHaveCount(0);

    await page.keyboard.press("6");
    await expect(page.getByRole("button", { name: /View changes/ }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Roll back to/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Restart/ })).toHaveCount(0);
    await page
      .getByRole("button", { name: /View changes/ })
      .first()
      .click();
    await expect(page.getByText("postgres-dr").first()).toBeVisible();

    await page.keyboard.press("5");
    await page.getByRole("button", { name: "config/app.env" }).click();
    await expect(page.getByRole("button", { name: /Deploy/ })).toHaveCount(0);
    await expect(page.getByLabel("Source of config/app.env")).toHaveAttribute("aria-readonly", "true");

    await page.keyboard.press("3");
    await expect(page.getByText("Busiest statements")).toBeVisible();
    await expect(page.getByText("Read-only query console")).toHaveCount(0);

    // The commands that were run stand where the terminal would be.
    await expect(page.getByText("devgrill status")).toBeVisible();
    await expect(page.locator(".xterm")).toHaveCount(0);
  });

  test("scores three answers and explains them, with nothing given away first", async ({ page }) => {
    await page.goto(`/case-files/${SLUG}`);
    const check = page.getByRole("button", { name: "Check my answers" });
    await expect(check).toBeDisabled();
    await expect(page.getByText("Where the evidence showed it")).toHaveCount(0);

    for (const name of ["What caused this?", /What do you do first/, "What is the durable fix?"]) {
      await page.getByRole("group", { name }).getByRole("radio").first().check();
    }
    await check.click();

    const heading = page.getByRole("heading", { name: /of 3 right/ });
    await expect(heading).toBeVisible();
    await expect(heading).toBeFocused();
    await expect(page.getByText(/Score \d+ of 100/)).toBeVisible();
    await expect(page.getByText("Where the evidence showed it")).toBeVisible();
    await expect(page.getByRole("link", { name: "Play it live" })).toHaveAttribute(
      "href",
      `/drills/databases/${SLUG}`,
    );
    // Guests are told what signing in would add.
    await expect(page.getByRole("link", { name: "Sign in with GitHub" })).toBeVisible();

    // A clue opens the panel it points at.
    await page.getByRole("button", { name: "Deploys" }).click();
    await expect(page.getByRole("button", { name: /View changes/ }).first()).toBeVisible();
  });

  test("is offered from the briefing", async ({ page }) => {
    await page.goto(`/drills/databases/${SLUG}`);
    await expect(page.getByRole("link", { name: "Open the case file" })).toHaveAttribute(
      "href",
      `/case-files/${SLUG}`,
    );
  });
});
