"use client";

import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { animate, useReducedMotionConfig } from "motion/react";
import { useEffect, useState } from "react";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * Rating change after a resolved incident. Counts up once on mount (the debrief's single
 * celebration moment); renders the final number immediately under reduced motion.
 * Reduced motion comes from MotionConfig (MotionPreferences), so the in-app setting applies.
 */
export function RatingDelta({
  delta,
  rating,
  track,
  animateOnMount = false,
  className,
}: {
  delta: number;
  rating: number;
  track: string;
  animateOnMount?: boolean;
  className?: string;
}) {
  const reduce = useReducedMotionConfig() ?? false;
  // Server and first client render agree; the effect then counts up or jumps to the end.
  const [shown, setShown] = useState(animateOnMount ? 0 : delta);

  useEffect(() => {
    if (!animateOnMount || reduce) {
      setShown(delta);
      return;
    }
    const controls = animate(0, delta, {
      duration: 0.8,
      ease: [0.05, 0.7, 0.1, 1],
      onUpdate: (v) => setShown(Math.round(v)),
    });
    return () => controls.stop();
  }, [delta, animateOnMount, reduce]);

  const up = delta > 0;
  const Icon = up ? ArrowUp : delta < 0 ? ArrowDown : Minus;
  const sign = up ? "+" : delta < 0 ? "−" : "±";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm px-2 py-1 font-mono text-mono font-semibold tabular-nums",
        up
          ? "bg-volt text-on-volt"
          : delta < 0
            ? "bg-danger-subtle text-danger-text"
            : "bg-raised text-fg-muted",
        className,
      )}
    >
      <span className="sr-only">{`${track} rating ${up ? "up" : delta < 0 ? "down" : "unchanged"} ${Math.abs(delta)}, now ${rating}`}</span>
      <Icon className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
      <span aria-hidden="true">
        {sign}
        {Math.abs(shown)}
      </span>
    </span>
  );
}
