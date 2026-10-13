import { Bricolage_Grotesque, Instrument_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";

/** UI sans (body, controls). Weight axis only, to keep the critical font small. */
export const fontUi = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-ui",
  display: "swap",
});

/** Editorial serif: briefings, debrief and postmortem headlines only. Never in the workspace. */
export const fontEditorial = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-editorial",
  display: "swap",
  preload: false,
});

/** Code and data: terminal, logs, IDs, timestamps, metrics. */
export const fontCode = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-code",
  display: "swap",
  // Not preloaded: mono text is never the largest paint and swaps without layout shift.
  preload: false,
});

/** Arcade layer only: share cards, streaks, Quick Fire, marketing hero. */
export const fontArcade = Bricolage_Grotesque({
  subsets: ["latin"],
  // Two static weights (~50 KB) instead of the full variable font with width/optical axes (128 KB).
  weight: ["700", "800"],
  variable: "--font-arcade",
  display: "swap",
  // Preloaded only where it is used (marketing and Quick Fire layouts apply its variable).
  preload: true,
});

/** Fonts available on every page. The Arcade face is added per layout (see fontArcade). */
export const fontVariables = [fontUi, fontEditorial, fontCode].map((f) => f.variable).join(" ");
