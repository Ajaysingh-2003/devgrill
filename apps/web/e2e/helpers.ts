import { expect, type Page } from "@playwright/test";
import pg from "pg";
import { IDP_URL, PG_URL } from "./stack.mjs";

/** Open a sign-in URL and press "Continue with GitHub" (retrying until hydrated). */
export async function startSignIn(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
  // A click before hydration does nothing: retry until the redirect to GitHub starts.
  const button = page.getByRole("button", { name: /Continue with GitHub|Opening GitHub/ });
  await expect(async () => {
    if (new URL(page.url()).pathname === "/sign-in") await button.click({ timeout: 2_000 });
    await page.waitForURL((u) => u.pathname !== "/sign-in", { timeout: 8_000 });
  }).toPass({ timeout: 30_000 });
}

/** Sign in through the real button and the mock GitHub, as `login`; wait to land on `next`. */
export async function signIn(page: Page, login: string, next = "/drills"): Promise<void> {
  await page.context().addCookies([{ name: "mock_user", value: login, url: IDP_URL }]);
  await startSignIn(page, `/sign-in?next=${encodeURIComponent(next)}`);
  await page.waitForURL((url) => url.pathname === next, { timeout: 20_000 });
  await expect(page.getByRole("link", { name: /Your profile/ })).toBeVisible();
}

/** Run SQL against the e2e database (setup and assertions that the UI can't reach). */
export async function sql<T = Record<string, unknown>>(text: string, params: unknown[] = []): Promise<T[]> {
  const client = new pg.Client({ connectionString: PG_URL });
  await client.connect();
  try {
    return (await client.query(text, params)).rows as T[];
  } finally {
    await client.end();
  }
}

/** Distinct logins per test run, so reruns against the same database don't collide. */
export function uniqueLogin(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 7)}`;
}
