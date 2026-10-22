"use client";

import { animate, motion, useMotionValue, useReducedMotionConfig, useTransform } from "motion/react";
import { useEffect, useState } from "react";
import { easingPoints } from "@devgrill/tokens";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * The debrief's single celebration (docs/PLAN.md §7.5): a check draws, the rating delta counts
 * up, the track bar fills. ~950 ms, once. Any click or key skips to the end; reduced motion
 * renders the end state immediately. Rare by design: never reused on frequent surfaces.
 */
export function VerifyCelebration({
  title,
  delta,
  rating,
  track,
  masteryBefore,
  masteryAfter,
  className,
}: {
  title: string;
  delta: number;
  rating: number;
  track: string;
  /** Track mastery 0–100 before and after this incident. */
  masteryBefore: number;
  masteryAfter: number;
  className?: string;
}) {
  // From MotionConfig (MotionPreferences): honours the in-app setting, not only the OS one.
  const reduce = useReducedMotionConfig() ?? false;
  const [skipped, setSkipped] = useState(false);
  const instant = reduce || skipped;
  // Server and first client render are identical (start state); reduced motion then jumps to
  // the end with zero-duration animations, so hydration never mismatches. The count is a
  // motion value written straight to the DOM: no React render per frame.
  const count = useMotionValue(0);
  const shown = useTransform(count, (v) => `+${Math.round(v)}`);

  // Any key skips the sequence (it never blocks reading the debrief).
  useEffect(() => {
    if (instant) return;
    const skip = () => setSkipped(true);
    window.addEventListener("keydown", skip, { once: true });
    return () => window.removeEventListener("keydown", skip);
  }, [instant]);

  useEffect(() => {
    const controls = animate(count, delta, {
      duration: instant ? 0 : 0.6,
      delay: instant ? 0 : 0.25,
      ease: easingPoints.enter,
    });
    return () => controls.stop();
  }, [count, delta, instant]);

  const t = (delay: number, duration: number) =>
    instant ? { duration: 0 } : { delay, duration, ease: easingPoints.enter };

  return (
    <div
      onClick={() => setSkipped(true)}
      className={cn("flex flex-wrap items-center gap-x-6 gap-y-4", className)}
    >
      <span className="grid size-14 shrink-0 place-items-center rounded-full bg-success-subtle text-success-text">
        <svg viewBox="0 0 24 24" className="size-7" aria-hidden="true">
          <motion.path
            d="M5 12.5l4.5 4.5L19 7.5"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={t(0, 0.4)}
          />
        </svg>
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h1 className="font-serif text-display-xl text-fg">{title}</h1>
        <p className="text-body-lg text-fg-muted">
          Graded on how the system behaved under attack, not on whether your code matched ours.
        </p>
      </div>

      <div className="flex w-full flex-col gap-2 sm:w-64">
        <div className="flex items-baseline justify-between">
          <span className="text-label text-fg-muted">{track} rating</span>
          <span className="rounded-sm bg-volt px-2 py-0.5 font-mono text-mono font-semibold text-on-volt tabular-nums">
            <span className="sr-only">{`Up ${delta}, now ${rating}`}</span>
            <motion.span aria-hidden="true">{shown}</motion.span>
          </span>
        </div>
        <div className="font-mono text-stat font-semibold text-fg tabular-nums">{rating}</div>
        <div
          role="img"
          aria-label={`${track} mastery from ${masteryBefore}% to ${masteryAfter}%`}
          className="relative h-1.5 overflow-hidden rounded-full bg-raised"
        >
          <span
            className="absolute inset-y-0 left-0 rounded-full bg-fg-subtle"
            style={{ width: `${masteryBefore}%` }}
          />
          {/* clip-path, not scaleX: scaling would squash the rounded end cap. */}
          <motion.span
            className="absolute inset-0 bg-brand"
            initial={{ clipPath: `inset(0 ${100 - masteryBefore}% 0 0 round 9999px)` }}
            animate={{ clipPath: `inset(0 ${100 - masteryAfter}% 0 0 round 9999px)` }}
            transition={t(0.45, 0.5)}
          />
        </div>
      </div>
    </div>
  );
}
