import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { contrastRatio, formatOklch, inSrgbGamut, maxChroma, parseOklch, toHex } from "./color.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("oklch math", () => {
  it("converts the extremes exactly", () => {
    expect(toHex(parseOklch("oklch(1 0 0)"))).toBe("#ffffff");
    expect(toHex(parseOklch("oklch(0 0 0)"))).toBe("#000000");
  });

  it("matches the palette validated during planning", () => {
    // Values cross-checked against the Python prototype (docs/PLAN.md §7.2).
    expect(toHex(parseOklch("oklch(0.52 0.098 215)"))).toBe("#00768c");
    expect(toHex(parseOklch("oklch(0.24 0.009 75)"))).toBe("#221f1b");
  });

  it("computes WCAG contrast", () => {
    const white = parseOklch("oklch(1 0 0)");
    const black = parseOklch("oklch(0 0 0)");
    expect(contrastRatio(white, black)).toBeCloseTo(21, 5);
    expect(contrastRatio(white, white)).toBeCloseTo(1, 5);
  });

  it("keeps maxChroma inside the sRGB gamut", () => {
    for (const hue of [25, 124, 210, 352]) {
      for (const l of [0.3, 0.6, 0.9]) {
        const c = maxChroma(l, hue);
        expect(inSrgbGamut({ l, c, h: hue, alpha: 1 })).toBe(true);
        expect(inSrgbGamut({ l, c: c + 0.02, h: hue, alpha: 1 })).toBe(false);
      }
    }
  });

  it("round-trips formatting, including alpha", () => {
    expect(formatOklch(parseOklch("oklch(0.24 0.009 75 / 0.45)"))).toBe("oklch(0.24 0.009 75 / 0.45)");
    expect(() => parseOklch("#ffffff")).toThrow();
  });
});

describe("generated tokens", () => {
  it("are up to date and every declared contrast pair passes", () => {
    // Exits non-zero if dist/ is stale or any pair fails.
    execFileSync(process.execPath, [join(ROOT, "src", "build.ts"), "--check"], { stdio: "pipe" });
    const report = JSON.parse(readFileSync(join(ROOT, "dist", "contrast.json"), "utf8"));
    expect(report.failures).toBe(0);
    expect(report.pairs).toBeGreaterThan(90);
  });
});
