import { durationsMs, easingPoints } from "@devgrill/tokens";

/**
 * Motion presets for `motion/react`, mirroring the CSS tokens (docs/PLAN.md §7.5).
 * Rules: keyboard-initiated changes are instant; nothing animates on streaming panels;
 * celebrate only on verify-passed and the debrief. Reduced motion is handled by
 * <MotionPreferences> via MotionConfig.
 */
const s = (ms: number) => ms / 1000;

export const transitions = {
  /** Hover, press, tab indicator, focus ring. */
  fast: { duration: s(durationsMs.fast), ease: easingPoints.standard },
  /** Popovers, dropdowns, sheets entering. */
  enter: { duration: s(durationsMs["base-in"]), ease: easingPoints.enter },
  /** Popovers, dropdowns, sheets leaving. */
  exit: { duration: s(durationsMs["base-out"]), ease: easingPoints.exit },
  /** Route transitions, opening the debrief. */
  slow: { duration: s(durationsMs.slow), ease: easingPoints.enter },
  /** Celebration springs (verify passed, rating delta). Interruptible by design. */
  celebrate: { type: "spring", stiffness: 260, damping: 26, mass: 0.9 },
  /** Keyboard-initiated: no animation at all. */
  instant: { duration: 0 },
} as const;
