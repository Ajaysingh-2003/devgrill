"use client";

import { useEffect, useState } from "react";

/** The sandbox hears about activity at most this often (the idle timeout is minutes long). */
const TOUCH_EVERY_MS = 60_000;
const ACTIVITY = ["keydown", "pointerdown", "wheel"] as const;

/**
 * Tells the sandbox someone is still working (keys, clicks, scrolling), so the idle timeout
 * only ends incidents nobody is playing. Returns when it last did, for the idle warning.
 * Listens in the capture phase: the terminal and editor stop their keys from bubbling.
 */
export function useActivityTouch(touch: () => Promise<void>, enabled: boolean): number {
  const [lastTouch, setLastTouch] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    let sent = Date.now();
    touch().catch(() => {});
    const onActivity = () => {
      const now = Date.now();
      if (now - sent < TOUCH_EVERY_MS) return;
      sent = now;
      setLastTouch(now);
      touch().catch(() => {
        // Best effort: the network banner covers a lost connection.
      });
    };
    for (const type of ACTIVITY) window.addEventListener(type, onActivity, { capture: true, passive: true });
    return () => {
      for (const type of ACTIVITY) window.removeEventListener(type, onActivity, { capture: true });
    };
  }, [touch, enabled]);
  return lastTouch;
}
