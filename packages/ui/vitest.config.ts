import { fileURLToPath } from "node:url";
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

const configDir = fileURLToPath(new URL("./.storybook", import.meta.url));

/**
 * Every story renders in Chromium, runs its play() interaction test and an axe audit.
 * The theme and motion globals are injected at build time and read by .storybook/preview.tsx.
 */
function storybookProject(name: string, globals: { theme: "light" | "dark"; motion: "full" | "reduce" }) {
  return {
    extends: true,
    plugins: [storybookTest({ configDir })],
    define: {
      "import.meta.env.VITE_SB_THEME": JSON.stringify(globals.theme),
      "import.meta.env.VITE_SB_MOTION": JSON.stringify(globals.motion),
    },
    test: {
      name,
      browser: {
        enabled: true,
        headless: true,
        provider: playwright(),
        instances: [{ browser: "chromium" as const }],
      },
    },
  };
}

export default defineConfig({
  test: {
    projects: [
      {
        extends: true,
        test: { name: "unit", include: ["src/**/*.test.ts"], environment: "node" },
      },
      storybookProject("storybook", { theme: "light", motion: "full" }),
      // Same stories again in the other theme with the in-app "Reduce motion" setting.
      storybookProject("storybook-dark-reduced", { theme: "dark", motion: "reduce" }),
    ],
  },
});
