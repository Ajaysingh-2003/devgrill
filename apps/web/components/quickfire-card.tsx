"use client";

import type { QuickfireAnswerOut, QuickfireCardOut } from "@devgrill/api-client";
import { Check, X } from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * One Quick Fire card: evidence, a question and its options. Controlled: the parent sends the
 * pick to the API and passes the result back, which reveals the answer and why.
 */
export function QuickFireCard({
  card,
  picked,
  result,
  busy = false,
  onPick,
}: {
  card: QuickfireCardOut;
  picked: string | null;
  result: QuickfireAnswerOut | null;
  busy?: boolean;
  onPick: (key: string) => void;
}) {
  const reveal = result !== null;
  return (
    <section
      aria-labelledby="qf-prompt"
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4"
    >
      <p className="text-caption text-fg-muted">{card.track_title}</p>
      <h1 id="qf-prompt" className="-mt-3 text-body-lg font-semibold text-fg">
        {card.prompt}
      </h1>
      <pre className="rounded-sm bg-sunken p-3 font-mono text-mono-sm leading-5 wrap-anywhere whitespace-pre-wrap text-fg">
        {card.evidence.join("\n")}
      </pre>
      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">Pick an answer (keys 1 to {card.options.length})</legend>
        {card.options.map((o, i) => {
          const isPicked = picked === o.key;
          const isCorrect = result?.answer === o.key;
          // Stay focusable after answering (aria-disabled, not disabled) so keyboard focus
          // doesn't fall back to <body>; the result is shown by icon + text, not colour alone.
          return (
            <button
              key={o.key}
              type="button"
              aria-disabled={reveal || busy}
              aria-keyshortcuts={String(i + 1)}
              onClick={() => {
                if (!reveal && !busy) onPick(o.key);
              }}
              aria-pressed={isPicked}
              className={cn(
                "flex min-h-12 items-center gap-2 rounded-sm border px-3 py-2.5 text-left text-body text-fg",
                !reveal && "border-border-input hover:bg-raised",
                !reveal && isPicked && "bg-raised",
                reveal && "cursor-default",
                reveal && isCorrect && "border-success-solid bg-success-subtle",
                reveal && isPicked && !isCorrect && "border-danger-solid bg-danger-subtle",
                reveal && !isPicked && !isCorrect && "border-border text-fg-muted",
              )}
            >
              <span aria-hidden="true" className="w-4 shrink-0 font-mono text-mono-sm text-fg-subtle">
                {i + 1}
              </span>
              <span className="flex-1">{o.text}</span>
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
        {result ? `${result.correct ? "Right." : "Not this time."} ${result.explanation_md}` : ""}
      </p>
    </section>
  );
}
