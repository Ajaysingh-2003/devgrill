/**
 * OKLCH colour math: gamut clamping, sRGB conversion and WCAG 2 contrast.
 * Pure functions, no dependencies, so the generator and the tests share one implementation.
 */

export type Oklch = { l: number; c: number; h: number; alpha: number };

const OKLCH_RE = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+))?\s*\)$/;

export function parseOklch(value: string): Oklch {
  const match = OKLCH_RE.exec(value.trim());
  if (!match) throw new Error(`Not an oklch() colour: ${value}`);
  const [, l, c, h, a] = match;
  return { l: Number(l), c: Number(c), h: Number(h), alpha: a === undefined ? 1 : Number(a) };
}

export function formatOklch({ l, c, h, alpha }: Oklch): string {
  const n = (x: number, digits: number) => String(Number(x.toFixed(digits)));
  const base = `${n(l, 3)} ${n(c, 3)} ${n(h, 3)}`;
  return alpha < 1 ? `oklch(${base} / ${n(alpha, 3)})` : `oklch(${base})`;
}

/** OKLCH → linear sRGB (may be out of [0, 1] when out of gamut). */
export function toLinearSrgb({ l, c, h }: Oklch): [number, number, number] {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
}

export function inSrgbGamut(color: Oklch, epsilon = 1e-4): boolean {
  return toLinearSrgb(color).every((v) => v >= -epsilon && v <= 1 + epsilon);
}

/** Largest chroma that stays inside sRGB for a given lightness and hue (binary search). */
export function maxChroma(l: number, h: number): number {
  let lo = 0;
  let hi = 0.4;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    if (inSrgbGamut({ l, c: mid, h, alpha: 1 })) lo = mid;
    else hi = mid;
  }
  return lo;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const gammaEncode = (v: number) => {
  const x = clamp01(v);
  return x <= 0.0031308 ? 12.92 * x : 1.055 * x ** (1 / 2.4) - 0.055;
};

export function toHex(color: Oklch): string {
  return (
    "#" +
    toLinearSrgb(color)
      .map((v) =>
        Math.round(gammaEncode(v) * 255)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

export function relativeLuminance(color: Oklch): number {
  const [r, g, b] = toLinearSrgb(color).map(clamp01) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG 2.x contrast ratio (1–21). Alpha is ignored; only use for opaque colours. */
export function contrastRatio(a: Oklch, b: Oklch): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
