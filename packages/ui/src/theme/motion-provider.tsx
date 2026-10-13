"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";
import { useTheme } from "./provider";

/**
 * Applies the reduced-motion preference (OS or in-app) to every motion/react animation below it.
 * Kept separate from ThemeProvider so pages without animation (e.g. the landing page) don't ship
 * the motion library.
 */
export function MotionPreferences({ children }: { children: ReactNode }) {
  const { reducedMotion } = useTheme();
  return <MotionConfig reducedMotion={reducedMotion ? "always" : "never"}>{children}</MotionConfig>;
}
