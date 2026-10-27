import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { signIn, sql, startSignIn, uniqueLogin } from "./helpers";
import { ADMIN_LOGIN, WEB_URL } from "./stack.mjs";

// Each sign-in is a chain of real redirects (web -> mock GitHub -> callback -> profile hook ->
// API -> claim -> page): give these tests room beyond the 30 s default.
test.describe.configure({ timeout: 60_000 });

test("GitHub sign-in creates the profile and shows the account", async ({ page }) => {
  const login = uniqueLogin("alice");
  await signIn(page, login);
  // The sign-in hook created the profile, with the GitHub login as the handle.
  const [profile] = await sql<{ handle: string }>("SELECT handle FROM app.profiles WHERE handle = $1", [
    login,
  ]);
  expect(profile?.handle).toBe(login);
  await page.getByRole("link", { name: /Your profile/ }).click();
  await expect(page).toHaveURL(new RegExp(`/u/${login}$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(login.replace(/-/g, " "));
  // Signed-in pages work.
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
});

test("signing out ends the session", async ({ page }) => {
  await signIn(page, uniqueLogin("bob"));
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: /Search or jump to/ }).click();
  await page.getByRole("combobox").fill("Sign out");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fsettings$/);
});

test("an expired session sends you back to sign-in", async ({ page }) => {
  const login = uniqueLogin("carol");
  await signIn(page, login);
  await sql(
    `UPDATE auth.session SET "expiresAt" = now() - interval '1 minute'
     WHERE "userId" = (SELECT id FROM auth."user" WHERE "githubLogin" = $1)`,
    [login],
  );
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Fsettings$/);
  await expect(page.getByRole("button", { name: "Continue with GitHub" })).toBeVisible();
});

test("sign-in never redirects off-site", async ({ page }) => {
  await page
    .context()
    .addCookies([{ name: "mock_user", value: uniqueLogin("dan"), url: "http://localhost:3999" }]);
  await startSignIn(page, "/sign-in?next=//evil.example/steal");
  await page.waitForURL((url) => url.pathname === "/drills", { timeout: 20_000 });
  expect(new URL(page.url()).host).toBe("localhost:3100");
});

test("guest tokens are issued as an httpOnly cookie", async ({ page }) => {
  await page.goto("/");
  const res = await page.request.post("/api/guest");
  expect(res.ok()).toBeTruthy();
  const cookie = (await page.context().cookies()).find((c) => c.name === "devgrill_guest");
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  // Asking again keeps the same guest identity.
  expect((await (await page.request.post("/api/guest")).json()).existing).toBe(true);
});

test("attempts played as a guest are claimed at sign-up", async ({ page }) => {
  await page.goto("/");
  await page.request.post("/api/guest");
  const token = (await page.context().cookies()).find((c) => c.name === "devgrill_guest")!.value;
  const { jti } = JSON.parse(Buffer.from(token.split(".")[1]!, "base64url").toString());
  const guestHash = createHash("sha256").update(jti).digest("hex");
  await sql(
    `INSERT INTO app.attempts (guest_token_hash, scenario_version_id, mode, state)
     SELECT $1, current_version_id, 'guided', 'abandoned' FROM app.scenarios WHERE slug = 'ttl-zero'`,
    [guestHash],
  );

  await signIn(page, uniqueLogin("erin"));
  const resume = page.getByRole("region", { name: "Pick up where you left off" });
  await expect(resume.getByRole("link", { name: /TTL zero/ })).toBeVisible();
  expect((await page.context().cookies()).some((c) => c.name === "devgrill_guest")).toBe(false);
  const [row] = await sql<{ claimed: boolean }>(
    "SELECT user_id IS NOT NULL AS claimed FROM app.attempts WHERE guest_token_hash = $1",
    [guestHash],
  );
  expect(row?.claimed).toBe(true);
});

test("the content console needs the admin role", async ({ browser }) => {
  test.slow(); // two full sign-ins
  const visitor = await browser.newPage();
  await signIn(visitor, uniqueLogin("frank"), "/drills");
  await visitor.goto("/admin");
  await expect(visitor.getByText("The content console needs the admin role")).toBeVisible();
  await visitor.close();

  const admin = await browser.newPage();
  await signIn(admin, ADMIN_LOGIN, "/drills");
  await admin.goto("/admin");
  await expect(admin.getByRole("rowheader", { name: "big-sale-meltdown" })).toBeVisible();
  await admin.close();
});

test("preferences follow the account to a new browser", async ({ browser, page }) => {
  test.slow(); // sign-in plus a second browser context
  const login = uniqueLogin("gina");
  await signIn(page, login, "/settings");
  await page.getByRole("main").getByRole("button", { name: "Dark" }).click();
  await page.getByRole("switch", { name: "Pro mode" }).click();
  await expect
    .poll(
      async () =>
        (
          await sql<{ prefs: Record<string, unknown> }>("SELECT prefs FROM app.profiles WHERE handle = $1", [
            login,
          ])
        )[0]?.prefs,
    )
    .toMatchObject({ theme: "dark", pro_mode: true });

  // Same account, fresh browser storage: the profile's theme is adopted.
  const fresh = await browser.newContext({
    storageState: { cookies: await page.context().cookies(), origins: [] },
  });
  const other = await fresh.newPage();
  await other.goto("/drills");
  await expect(other.locator("html")).toHaveClass(/dark/);
  await other.goto("/settings");
  await expect(other.getByRole("switch", { name: "Pro mode" })).toBeChecked();
  await fresh.close();
});

test("the GitHub login can't be changed after sign-up (it decides admin roles)", async ({ page }) => {
  const login = uniqueLogin("mallory");
  await signIn(page, login);
  const update = (data: Record<string, string>) =>
    // From the user's own browser (same origin): CSRF protection doesn't apply, our hooks must.
    page.request.post("/api/auth/update-user", { headers: { Origin: WEB_URL }, data });

  const sneaky = await update({ githubLogin: ADMIN_LOGIN, name: "Mallory" });
  expect(sneaky.status()).toBe(400);
  const honest = await update({ name: "Mallory" });
  expect(honest.ok(), await honest.text()).toBeTruthy();

  const [user] = await sql<{ githubLogin: string; name: string }>(
    `SELECT "githubLogin", name FROM auth."user" WHERE email = $1`,
    [`${login}@example.test`],
  );
  expect(user).toEqual({ githubLogin: login, name: "Mallory" });
});

test("cross-site requests to the auth API are refused", async ({ page }) => {
  await signIn(page, uniqueLogin("trent"));
  const res = await page.request.post("/api/auth/update-user", {
    headers: { Origin: "https://evil.example" },
    data: { name: "Pwned" },
  });
  expect(res.status()).toBe(403);
});
