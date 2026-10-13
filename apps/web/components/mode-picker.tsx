"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@devgrill/ui/lib/utils";

const MODES = [
  {
    id: "guided",
    name: "Guided",
    desc: "Three tiered hints and an AI mentor. The clock is hidden and your rating changes less.",
  },
  {
    id: "oncall",
    name: "Real on-call",
    desc: "No hints, the clock counts and teammates get impatient. Fully rated.",
  },
] as const;

export function ModePicker({ scenarioSlug }: { scenarioSlug: string }) {
  const [mode, setMode] = useState<string>("guided");
  return (
    <div className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4">
      <h2 id="mode-label" className="text-body font-semibold text-fg">
        How do you want to play?
      </h2>
      <RadioGroup
        aria-labelledby="mode-label"
        value={mode}
        onValueChange={(v) => setMode(String(v))}
        className="flex flex-col gap-2"
      >
        {MODES.map((m) => (
          <Radio.Root
            key={m.id}
            value={m.id}
            className={cn(
              "flex flex-col gap-1 rounded-sm border px-3 py-2.5 text-left outline-none",
              "border-border hover:bg-raised data-[checked]:border-brand data-[checked]:bg-brand-subtle",
              "focus-visible:ring-2 focus-visible:ring-focus-ring",
            )}
          >
            <span className="text-body font-semibold text-fg">{m.name}</span>
            <span className="text-label text-fg-muted">{m.desc}</span>
          </Radio.Root>
        ))}
      </RadioGroup>
      <Link
        href={`/incident/inc-4021?scenario=${scenarioSlug}&mode=${mode}`}
        className="inline-flex h-10 items-center justify-center rounded-sm bg-brand text-body font-semibold text-on-brand hover:bg-brand-hover"
      >
        Start the incident
      </Link>
      <p className="text-caption text-fg-subtle">
        Your sandbox starts in about 20 seconds and stops after 45 minutes.
      </p>
    </div>
  );
}
