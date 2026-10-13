import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

export type BootStepState = "pending" | "active" | "done" | "failed";
export type BootStep = { id: string; label: string; detail?: string; state: BootStepState };

/**
 * Sandbox provisioning narrated with real workflow states, never a fake progress bar.
 * The active step is announced politely to screen readers.
 */
export function BootSequence({ steps, title }: { steps: BootStep[]; title: string }) {
  const active = steps.find((s) => s.state === "active" || s.state === "failed");
  return (
    <section aria-labelledby="boot-title" className="flex flex-col gap-4">
      <h2 id="boot-title" className="text-heading-md font-semibold text-fg">
        {title}
      </h2>
      <ol className="flex flex-col">
        {steps.map((step, i) => (
          <li key={step.id} className="grid grid-cols-[1.25rem_1fr] gap-x-3">
            <span className="flex flex-col items-center">
              <StepIcon state={step.state} />
              {i < steps.length - 1 ? (
                <span
                  aria-hidden="true"
                  className={cn("w-px flex-1", step.state === "done" ? "bg-success-solid" : "bg-border")}
                />
              ) : null}
            </span>
            <span className="flex flex-col pb-4">
              <span
                className={cn(
                  "text-body",
                  step.state === "pending" ? "text-fg-subtle" : "text-fg",
                  step.state === "active" && "font-medium",
                )}
              >
                {step.label}
                <span className="sr-only">, {step.state}</span>
              </span>
              {step.detail ? (
                <span className="font-mono text-mono-sm text-fg-subtle">{step.detail}</span>
              ) : null}
            </span>
          </li>
        ))}
      </ol>
      <p aria-live="polite" className="sr-only">
        {active ? `${active.label}${active.state === "failed" ? " failed" : ""}` : "Sandbox ready"}
      </p>
    </section>
  );
}

function StepIcon({ state }: { state: BootStepState }) {
  const base = "relative z-10 grid size-5 place-items-center rounded-full";
  if (state === "done")
    return (
      <span className={cn(base, "bg-success-solid text-on-success")}>
        <Check className="size-3" strokeWidth={3} aria-hidden="true" />
      </span>
    );
  if (state === "failed")
    return (
      <span className={cn(base, "bg-danger-solid text-on-danger")}>
        <X className="size-3" strokeWidth={3} aria-hidden="true" />
      </span>
    );
  if (state === "active")
    return (
      <span className={cn(base, "bg-brand-subtle text-brand-text")}>
        <LoaderCircle className="size-3.5 motion-safe:animate-spin" strokeWidth={2.5} aria-hidden="true" />
      </span>
    );
  return (
    <span className={cn(base, "bg-surface text-fg-subtle")}>
      <Circle className="size-3" strokeWidth={2} aria-hidden="true" />
    </span>
  );
}
