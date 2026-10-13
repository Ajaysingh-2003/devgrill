"use client";

import { useSyncExternalStore } from "react";

const noopSubscribe = () => () => {};

/** True on macOS (for ⌘ vs Ctrl labels). False during SSR; corrected on hydration without an effect. */
export function useIsMac(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => navigator.platform.toLowerCase().includes("mac"),
    () => false,
  );
}
