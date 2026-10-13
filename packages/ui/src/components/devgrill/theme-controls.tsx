"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type MotionPreference, type ThemePreference } from "@devgrill/ui/theme";
import { cn } from "@devgrill/ui/lib/utils";

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

/**
 * Compact three-way theme switch for the top bar: a labelled group of toggle buttons
 * (aria-pressed), each its own Tab stop. Not role=radio, which would promise arrow-key handling.
 */
export function ThemeSwitch({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="group"
      aria-label="Theme"
      className={cn("inline-flex rounded-sm border border-border p-0.5", className)}
    >
      {THEMES.map(({ value, label, icon: Icon }) => {
        const checked = theme === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={checked}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            className={cn(
              "grid size-7 place-items-center rounded-xs outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
              checked ? "bg-raised text-fg" : "text-fg-subtle hover:text-fg",
            )}
          >
            <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}

const MOTION: { value: MotionPreference; label: string; hint: string }[] = [
  { value: "system", label: "Match my device", hint: "Follows your operating system setting." },
  { value: "reduce", label: "Reduce motion", hint: "Replaces movement with instant changes." },
  { value: "full", label: "Full motion", hint: "Plays transitions even if your device asks to reduce them." },
];

/** Settings control for motion (in addition to the OS preference). */
export function MotionSetting() {
  const { motion, setMotion } = useTheme();
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-body font-semibold text-fg">Motion</legend>
      {MOTION.map((m) => (
        <label
          key={m.value}
          className="flex cursor-pointer items-start gap-3 rounded-sm px-2 py-1.5 hover:bg-raised"
        >
          <input
            type="radio"
            name="motion"
            value={m.value}
            checked={motion === m.value}
            onChange={() => setMotion(m.value)}
            className="mt-1 accent-[var(--brand)]"
          />
          <span className="flex flex-col">
            <span className="text-body text-fg">{m.label}</span>
            <span className="text-label text-fg-muted">{m.hint}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
