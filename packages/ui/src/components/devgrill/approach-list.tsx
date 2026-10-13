"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { cn } from "@devgrill/ui/lib/utils";

export type ApproachOutcome = "full" | "partial" | "fails";

export type Approach = {
  id: string;
  name: string;
  /** Share of solvers who used it, 0–100. */
  share: number;
  outcome: ApproachOutcome;
  yours?: boolean;
};

const OUTCOME: Record<ApproachOutcome, { label: string; tone: string }> = {
  full: { label: "Passes", tone: "bg-success-subtle text-success-text" },
  partial: { label: "Partial", tone: "bg-warning-subtle text-warning-text" },
  fails: { label: "Fails", tone: "bg-danger-subtle text-danger-text" },
};

/**
 * "Your fix vs every other approach players tried". A radio group: one approach is
 * inspected at a time; arrow keys move between them.
 */
export function ApproachList({
  approaches,
  value,
  onValueChange,
  label,
}: {
  approaches: Approach[];
  value: string;
  onValueChange: (id: string) => void;
  label: string;
}) {
  return (
    <RadioGroup
      aria-label={label}
      value={value}
      onValueChange={(v) => onValueChange(String(v))}
      className="flex flex-col gap-1.5"
    >
      {approaches.map((a) => (
        <Radio.Root
          key={a.id}
          value={a.id}
          className={cn(
            "group grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5 rounded-md border px-3 py-2.5 text-left",
            "border-border bg-surface transition-colors duration-[var(--duration-fast)] ease-standard",
            "hover:bg-raised data-[checked]:border-brand data-[checked]:bg-brand-subtle",
            "outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-canvas",
          )}
        >
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-body font-medium text-fg">{a.name}</span>
            <span className="text-caption text-fg-muted">
              {a.share}% of solvers{a.yours ? ", including you" : ""}
            </span>
          </span>
          <span className={cn("rounded-xs px-1.5 py-0.5 text-caption font-medium", OUTCOME[a.outcome].tone)}>
            {OUTCOME[a.outcome].label}
          </span>
          <span className="col-span-2 h-1 overflow-hidden rounded-full bg-raised" aria-hidden="true">
            <span className="block h-full rounded-full bg-fg-subtle" style={{ width: `${a.share}%` }} />
          </span>
        </Radio.Root>
      ))}
    </RadioGroup>
  );
}
