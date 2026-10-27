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

test("on-call leave is booked and cancelled in Settings", async ({ page }) => {
  await signIn(page, uniqueLogin("lena"), "/settings");
  const leave = page.getByRole("region", { name: "On-call leave" });
  await expect(leave.getByText("No leave booked.")).toBeVisible();
  // Tomorrow to the day after, in the player's own calendar (dates are plain strings).
  const today = await leave.getByLabel("From").getAttribute("min");
  const next = new Date(Date.parse(`${today}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
  const later = new Date(Date.parse(`${next}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
  await leave.getByLabel("From").fill(next);
  await leave.getByLabel("To (optional)").fill(later);
  await leave.getByRole("button", { name: "Book leave" }).click();
  await expect(leave.getByRole("listitem")).toHaveCount(1);
  await expect(leave.getByRole("listitem")).toContainText(" to ");
  await page.reload();
  await expect(leave.getByRole("listitem")).toHaveCount(1);
  await leave.getByRole("button", { name: /^Cancel leave/ }).click();
  await expect(leave.getByText("No leave booked.")).toBeVisible();
});

test("the daily email can be turned on, and the pause page needs a valid link", async ({ page }) => {
  await signIn(page, uniqueLogin("mira"), "/settings");
  const email = page.getByRole("region", { name: "Daily email" });
  // The mock GitHub shares an email, so the switch is there.
  await email.getByRole("switch", { name: "Daily email" }).click();
  await expect(email.getByRole("switch", { name: "Daily email" })).toBeChecked();
  await email.getByLabel("Send it at").selectOption("18");
  await page.goto("/emails/pause?token=forged.token");
  await page.getByRole("button", { name: "Pause emails" }).click();
  await expect(page.getByRole("heading", { name: "This link didn’t work" })).toBeVisible();
});
