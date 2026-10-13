import type { Decorator, Preview } from "@storybook/react-vite";
import { useLayoutEffect } from "react";
import { MOTION_STORAGE_KEY, THEME_STORAGE_KEY, ThemeProvider } from "../src/theme";
import { MotionPreferences } from "../src/theme/motion-provider";
import "./storybook.css";

/**
 * Theme and motion come from the toolbar. The decorator writes them where the real app keeps
 * them (localStorage + <html>), so components render exactly as they do in the product.
 */
const withDevGrillTheme: Decorator = (Story, context) => {
  const theme = (context.globals.theme as string) ?? "light";
  const motion = (context.globals.motion as string) ?? "full";
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
    localStorage.setItem(MOTION_STORAGE_KEY, motion);
  } catch {
    // Storage unavailable in some test runners: the class below still applies.
  }
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(theme);
    root.setAttribute("data-motion", motion);
  }, [theme, motion]);
  return (
    <ThemeProvider>
      <MotionPreferences>
        <Story />
      </MotionPreferences>
    </ThemeProvider>
  );
};

// The test runner sets these per Vitest project (vitest.config.ts); the UI defaults to light/full.
const env = import.meta.env as Record<string, string | undefined>;
const initialTheme = env.VITE_SB_THEME ?? "light";
const initialMotion = env.VITE_SB_MOTION ?? "full";

const preview: Preview = {
  decorators: [withDevGrillTheme],
  globalTypes: {
    theme: {
      description: "Colour theme",
      toolbar: { title: "Theme", icon: "mirror", items: ["light", "dark"], dynamicTitle: true },
    },
    motion: {
      description: "Motion preference",
      toolbar: { title: "Motion", icon: "play", items: ["full", "reduce"], dynamicTitle: true },
    },
  },
  initialGlobals: { theme: initialTheme, motion: initialMotion },
  parameters: {
    layout: "padded",
    // Accessibility violations fail the story test (docs/PLAN.md phase 1 gate).
    a11y: { test: "error" },
    controls: { expanded: true },
  },
};

export default preview;
