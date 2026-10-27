import { expect, test } from "@playwright/test";
import { signIn, sql, uniqueLogin } from "./helpers";

test.describe.configure({ timeout: 60_000 });

test("a new account picks its experience, answers six cards and gets starting ratings", async ({ page }) => {
  const login = uniqueLogin("erin");
  await signIn(page, login, "/onboarding");
  await expect(page.getByRole("heading", { name: /Welcome/ })).toBeVisible();
  await page.getByRole("radio", { name: "2 to 5 years" }).check();
  await page.getByRole("radio", { name: "Backend" }).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Answer six cards" }).click();

  for (let i = 1; i <= 6; i += 1) {
    await expect(page.getByText(`Card ${i} of 6`)).toBeVisible();
    await page.getByRole("main").getByRole("group").getByRole("button").first().click();
    await expect(page.getByText(/^(Right|Not this time)\./)).toBeVisible();
    await page.getByRole("button", { name: i === 6 ? "Finish" : "Next card" }).click();
  }
  await expect(page.getByRole("heading", { name: "You’re set" })).toBeVisible();
  await expect(page.getByText(/of 6 right/)).toBeVisible();

  const [profile] = await sql<{ experience_level: string; onboarded: boolean }>(
    "SELECT experience_level, (prefs->>'onboarded')::boolean AS onboarded FROM app.profiles WHERE handle = $1",
    [login],
  );
  expect(profile).toEqual({ experience_level: "2-5", onboarded: true });
  const [ratings] = await sql<{ n: number }>(
    `SELECT count(*)::int AS n FROM app.skill_ratings r JOIN app.profiles p ON p.user_id = r.user_id
     WHERE p.handle = $1 AND r.games = 0`,
    [login],
  );
  expect(ratings?.n).toBe(6);
});

test("Quick Fire answers by keyboard and explains each card", async ({ page }) => {
  await page.goto("/quickfire");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("0 answered, 0 right")).toBeVisible();
  await page.keyboard.press("1");
  await expect(page.getByText(/^(Right|Not this time)\./)).toBeVisible();
  await expect(page.getByText(/1 answered/)).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/^(Right|Not this time)\./)).toBeHidden();
});
