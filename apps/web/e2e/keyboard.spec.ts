import { expect, test, type Page } from "@playwright/test";

/** Navigate and wait until the page is hydrated (dev builds compile on first hit). */
async function open(page: Page, url: string) {
  await page.goto(url);
  await page.waitForLoadState("networkidle");
}

const mod = process.platform === "darwin" ? "Meta" : "Control";

for (const route of ["/", "/drills", "/incident/demo", "/incident/demo/debrief", "/quickfire"]) {
  test(`skip link is the first stop on ${route} and targets the main landmark`, async ({ page }) => {
    await page.goto(route);
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Skip to content" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeVisible();
    await expect(page.locator("main#main")).toHaveCount(1);
  });
}

test("command palette opens with the keyboard and navigates", async ({ page }) => {
  await open(page, "/drills");
  await page.keyboard.press(`${mod}+k`);
  const input = page.getByRole("combobox");
  await expect(input).toBeFocused();
  await input.fill("daily");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/daily$/);
});

test("drill filters narrow the list and clear again", async ({ page }) => {
  await open(page, "/drills");
  const list = page.getByRole("region", { name: "All drills" });
  const count = list.getByText(/^\d+ drills$/);
  const total = Number((await count.textContent())!.split(" ")[0]);
  await list.getByRole("searchbox", { name: "Search drills" }).fill("ttl");
  await expect(list.getByText(`1 of ${total} drills`)).toBeVisible();
  await expect(list.getByRole("link", { name: /TTL zero/ })).toBeVisible();
  await list.getByRole("group", { name: "Severity" }).getByRole("button", { name: /SEV1/ }).click();
  await expect(list.getByText("No drills match these filters.")).toBeVisible();
  await list.getByRole("button", { name: "Clear filters" }).last().click();
  await expect(list.getByText(`${total} drills`)).toBeVisible();
});

test("theme choice persists across reloads", async ({ page }) => {
  await open(page, "/drills");
  await page
    .getByRole("banner")
    .getByRole("group", { name: "Theme" })
    .getByRole("button", { name: "Dark" })
    .click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test.describe("incident workspace", () => {
  test("number keys switch tools, but not while typing", async ({ page }) => {
    await open(page, "/incident/demo");
    await page.getByRole("tab", { name: /Overview/ }).waitFor();
    await expect(async () => {
      await page.keyboard.press("2");
      await expect(page.getByRole("tab", { name: "Logs" })).toHaveAttribute("aria-selected", "true", {
        timeout: 1000,
      });
    }).toPass();
    await page.getByLabel("Log query").focus();
    await page.keyboard.press("3");
    await expect(page.getByRole("tab", { name: "Logs" })).toHaveAttribute("aria-selected", "true");
  });

  test("collapsed panels leave the tab order", async ({ page }) => {
    await open(page, "/incident/demo");
    await page.getByRole("tab", { name: /Overview/ }).waitFor();
    // Focus mode collapses the terminal and the team chat to 0px: they must not hold focus.
    await page.getByRole("region", { name: "Overview" }).focus();
    await page.keyboard.press("f");
    const inert = page.locator("[inert]");
    await expect(inert).toHaveCount(2);
    await expect(inert.getByRole("heading", { name: "Terminal" })).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(inert).toHaveCount(0);
  });

  test("splitters resize with the keyboard (WAI-ARIA window splitter)", async ({ page }) => {
    await open(page, "/incident/demo");
    // The team chat's splitter moves left and right; the terminal's (across the bottom) up and down.
    for (const [name, key] of [
      [/work area and the team chat/, "ArrowLeft"],
      [/tool panel and the terminal/, "ArrowUp"],
    ] as const) {
      const separator = page.getByRole("separator", { name });
      const before = Number(await separator.getAttribute("aria-valuenow"));
      await separator.focus();
      await page.keyboard.press(key);
      await page.keyboard.press(key);
      await expect
        .poll(async () => Number(await separator.getAttribute("aria-valuenow")))
        .toBeLessThan(before);
    }
  });

  test("F maximises the focused panel and Escape restores it", async ({ page }) => {
    await open(page, "/incident/demo");
    await page.getByRole("tab", { name: /Overview/ }).waitFor();
    // Focus the primary panel's scrollable body (a focusable region), then press F.
    await page.getByRole("region", { name: "Overview" }).focus();
    await page.keyboard.press("f");
    await expect(page.getByText("Tool panel maximised. Press Escape to restore.")).toBeAttached();
    await page.keyboard.press("Escape");
    await expect(page.getByText("Tool panel maximised. Press Escape to restore.")).not.toBeAttached();
  });

  test("below 1024 px it offers alternatives instead of a cramped workspace", async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 800 });
    await open(page, "/incident/demo");
    await expect(page.getByRole("heading", { name: "This drill needs a bigger screen" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Play Quick Fire" })).toBeVisible();
  });
});

/** Records every "+N" value the rating counter shows, from before hydration onwards. */
async function recordRatingValues(page: Page) {
  await page.addInitScript(() => {
    const seen = new Set<string>();
    (window as unknown as { __ratingValues: Set<string> }).__ratingValues = seen;
    new MutationObserver((records) => {
      for (const r of records) {
        const text = (r.target.nodeType === Node.TEXT_NODE ? r.target.parentElement : r.target)?.textContent;
        if (text && /^\+\d+$/.test(text)) seen.add(text);
      }
    }).observe(document, { subtree: true, childList: true, characterData: true });
  });
}
const ratingValues = (page: Page) =>
  page.evaluate(() => [...(window as unknown as { __ratingValues: Set<string> }).__ratingValues]);

test.describe("reduced motion", () => {
  test("OS setting: the debrief jumps straight to the final rating", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await recordRatingValues(page);
    await page.goto("/incident/demo/debrief");
    await expect(page.getByText("+52", { exact: true })).toBeVisible();
    expect((await ratingValues(page)).filter((v) => v !== "+0" && v !== "+52")).toEqual([]);
  });

  test("in-app setting: overrides an OS that allows motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.addInitScript(() => localStorage.setItem("devgrill-motion", "reduce"));
    await recordRatingValues(page);
    await page.goto("/incident/demo/debrief");
    await expect(page.getByText("+52", { exact: true })).toBeVisible();
    expect((await ratingValues(page)).filter((v) => v !== "+0" && v !== "+52")).toEqual([]);
  });

  test("full motion counts up through intermediate values", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await recordRatingValues(page);
    await page.goto("/incident/demo/debrief");
    await expect(page.getByText("+52", { exact: true })).toBeVisible();
    expect((await ratingValues(page)).filter((v) => v !== "+0" && v !== "+52").length).toBeGreaterThan(0);
  });
});
