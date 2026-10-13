// Capture template screenshots in both themes at several widths for design QC.
// Usage: node scripts/screenshots.mjs <outDir> <path> [path...]
//   env WIDTHS="1440,1024,390" THEMES="light,dark" BASE=http://localhost:3000 FULL=1 FORMAT=png|jpeg
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const [outDir, ...paths] = process.argv.slice(2);
if (!outDir || !paths.length) {
  console.error("usage: node scripts/screenshots.mjs <outDir> <path> [path...]");
  process.exit(2);
}
const base = process.env.BASE ?? "http://localhost:3000";
const widths = (process.env.WIDTHS ?? "1440,1024,390").split(",").map(Number);
const themes = (process.env.THEMES ?? "light,dark").split(",");
const fullPage = process.env.FULL !== "0";
// JPEG keeps committed QC evidence small; PNG for pixel-level review.
const format = process.env.FORMAT === "jpeg" ? "jpeg" : "png";
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
for (const theme of themes) {
  for (const width of widths) {
    const context = await browser.newContext({
      viewport: { width, height: width < 600 ? 844 : 900 },
      deviceScaleFactor: 1,
      reducedMotion: "reduce",
    });
    await context.addInitScript((t) => localStorage.setItem("devgrill-theme", t), theme);
    const page = await context.newPage();
    for (const path of paths) {
      await page.goto(base + path, { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      const name = `${path === "/" ? "home" : path.slice(1).replace(/[/?=&]/g, "_")}--${theme}--${width}.${format === "jpeg" ? "jpg" : "png"}`;
      await page.screenshot({
        path: join(outDir, name),
        fullPage,
        type: format,
        ...(format === "jpeg" ? { quality: 72 } : {}),
      });
      console.log("saved", name);
    }
    await context.close();
  }
}
await browser.close();
