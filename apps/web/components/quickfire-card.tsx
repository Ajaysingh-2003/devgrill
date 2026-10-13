"use client";

import { useState } from "react";
import { Check, X } from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

export function QuickFireCard({
  prompt,
  evidence,
  options,
}: {
  prompt: string;
  evidence: string[];
  options: { id: string; label: string }[];
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const correct = "a";
  return (
    <section
      aria-labelledby="qf-prompt"
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4"
    >
      <h1 id="qf-prompt" className="text-body-lg font-semibold text-fg">
        {prompt}
      </h1>
      <pre className="rounded-sm bg-sunken p-3 font-mono text-mono-sm leading-5 wrap-anywhere whitespace-pre-wrap text-fg">
        {evidence.join("\n")}
      </pre>
      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">Pick the most likely cause</legend>
        {options.map((o) => {
          const isPicked = picked === o.id;
          const reveal = picked !== null;
          const isCorrect = o.id === correct;
          // Stay focusable after answering (aria-disabled, not disabled) so keyboard focus
          // doesn't fall back to <body>; the result is shown by icon + text, not colour alone.
          return (
            <button
              key={o.id}
              type="button"
              aria-disabled={reveal}
              onClick={() => {
                if (!reveal) setPicked(o.id);
              }}
              aria-pressed={isPicked}
              className={cn(
                "flex min-h-12 items-center gap-2 rounded-sm border px-3 py-2.5 text-left text-body text-fg",
                !reveal && "border-border-input hover:bg-raised",
                reveal && "cursor-default",
                reveal && isCorrect && "border-success-solid bg-success-subtle",
                reveal && isPicked && !isCorrect && "border-danger-solid bg-danger-subtle",
                reveal && !isPicked && !isCorrect && "border-border text-fg-muted",
              )}
            >
              <span className="flex-1">{o.label}</span>
              {reveal && isCorrect ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-label font-medium text-success-text">
                  <Check className="size-4" aria-hidden="true" />
                  Correct
                </span>
              ) : null}
              {reveal && isPicked && !isCorrect ? (
                <span className="inline-flex shrink-0 items-center gap-1 text-label font-medium text-danger-text">
                  <X className="size-4" aria-hidden="true" />
                  Your pick
                </span>
              ) : null}
            </button>
          );
        })}
      </fieldset>
      <p aria-live="polite" className="text-body text-fg-muted">
        {picked === null
          ? ""
          : picked === correct
            ? "Right. The sequential scan on orders started with the deploy: an index on user_id went missing."
            : "Not this time. The sequential scan right after the deploy points to a dropped index."}
      </p>
    </section>
  );
}
