"use client";

import { cn } from "@devgrill/ui/lib/utils";

/** Which service a panel shows, when the incident has more than one to edit or deploy. */
export function ServicePicker({
  services,
  value,
  onPick,
  disabled,
}: {
  services: string[];
  value: string;
  onPick: (service: string) => void;
  disabled?: boolean;
}) {
  if (services.length < 2) return null;
  return (
    <div role="group" aria-label="Service" className="flex rounded-sm border border-border-input p-0.5">
      {services.map((s) => (
        <button
          key={s}
          type="button"
          aria-pressed={s === value}
          disabled={disabled}
          onClick={() => s !== value && onPick(s)}
          className={cn(
            "h-6 rounded-xs px-2 font-mono text-mono-sm disabled:opacity-60",
            s === value ? "bg-brand-subtle text-brand-text" : "text-fg-muted hover:bg-raised hover:text-fg",
          )}
        >
          {s}
        </button>
      ))}
    </div>
  );
}
