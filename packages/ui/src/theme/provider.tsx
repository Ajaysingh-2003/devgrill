"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { themeColors } from "@devgrill/tokens";
import { MOTION_STORAGE_KEY, THEME_STORAGE_KEY } from "./script";

export type ThemePreference = "system" | "light" | "dark";
export type MotionPreference = "system" | "reduce" | "full";

type ThemeContextValue = {
  theme: ThemePreference;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: ThemePreference) => void;
  motion: MotionPreference;
  reducedMotion: boolean;
  setMotion: (motion: MotionPreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

/*
 * Preferences live in localStorage and are read through useSyncExternalStore, so React reads
 * them during hydration (no effect + setState round trip) and other tabs stay in sync.
 */
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

function subscribeStorage(onChange: () => void) {
  listeners.add(onChange);
  const onStorage = (e: StorageEvent) => {
    if (e.key === THEME_STORAGE_KEY || e.key === MOTION_STORAGE_KEY) onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function readPref<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key);
    return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage disabled: the preference still applies until the page reloads.
  }
  emit();
}

const THEMES = ["system", "light", "dark"] as const;
const MOTIONS = ["system", "reduce", "full"] as const;

function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => matchMedia(query).matches,
    () => false,
  );
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(
    subscribeStorage,
    () => readPref(THEME_STORAGE_KEY, THEMES, "system"),
    () => "system" as ThemePreference,
  );
  const motion = useSyncExternalStore(
    subscribeStorage,
    () => readPref(MOTION_STORAGE_KEY, MOTIONS, "system"),
    () => "system" as MotionPreference,
  );
  const systemDark = useMediaQuery("(prefers-color-scheme: dark)");
  const systemReduce = useMediaQuery("(prefers-reduced-motion: reduce)");

  const resolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme;
  const reducedMotion = motion === "reduce" || (motion === "system" && systemReduce);

  // Keep <html> in sync (the inline script handled the first paint).
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(resolvedTheme);
    // Browser chrome follows the app's theme, not only the OS one (the meta tags carry
    // media queries for the first paint; an explicit choice overrides both).
    for (const meta of document.querySelectorAll('meta[name="theme-color"]')) {
      meta.setAttribute("content", themeColors[resolvedTheme].canvas);
    }
  }, [resolvedTheme]);

  useEffect(() => {
    const root = document.documentElement;
    if (motion === "system") root.removeAttribute("data-motion");
    else root.setAttribute("data-motion", motion);
  }, [motion]);

  const setTheme = useCallback((next: ThemePreference) => writePref(THEME_STORAGE_KEY, next), []);
  const setMotion = useCallback((next: MotionPreference) => writePref(MOTION_STORAGE_KEY, next), []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, motion, reducedMotion, setMotion }),
    [theme, resolvedTheme, setTheme, motion, reducedMotion, setMotion],
  );

  // Motion preferences for motion/react are applied by <MotionPreferences> where animation is used.
  return <ThemeContext value={value}>{children}</ThemeContext>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
