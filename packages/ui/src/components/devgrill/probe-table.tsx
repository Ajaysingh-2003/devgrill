import { Check, Loader, Minus, X, type LucideIcon } from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

/** `skipped`: the run ended (on our side) before this probe ran. */
export type ProbeOutcome = "pass" | "fail" | "partial" | "running" | "queued" | "skipped";

export type Probe = {
  key: string;
  name: string;
  /** How the probe attacks the system, in one line. */
  how: string;
  observed?: string;
  target: string;
  outcome: ProbeOutcome;
};

const OUTCOME: Record<ProbeOutcome, { label: string; icon: LucideIcon; tone: string }> = {
  pass: { label: "Pass", icon: Check, tone: "bg-success-subtle text-success-text" },
  fail: { label: "Fail", icon: X, tone: "bg-danger-subtle text-danger-text" },
  partial: { label: "Partial", icon: Minus, tone: "bg-warning-subtle text-warning-text" },
  running: { label: "Running", icon: Loader, tone: "bg-info-subtle text-info-text" },
  queued: { label: "Queued", icon: Minus, tone: "bg-raised text-fg-subtle" },
  skipped: { label: "Not run", icon: Minus, tone: "bg-raised text-fg-subtle" },
};

export function ProbeOutcomeBadge({ outcome }: { outcome: ProbeOutcome }) {
  const { label, icon: Icon, tone } = OUTCOME[outcome];
  return (
    <span
      className={cn(
        "inline-flex w-[5.5rem] items-center gap-1.5 rounded-xs px-1.5 py-0.5 text-caption font-medium",
        tone,
      )}
    >
      <Icon
        className={cn("size-3.5", outcome === "running" && "motion-safe:animate-spin")}
        strokeWidth={2.25}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

/** What verify threw at the fix. A real table: probes are compared across columns. */
export function ProbeTable({ probes, caption }: { probes: Probe[]; caption: string }) {
  return (
    // Scrolls sideways on narrow screens; focusable so keyboard users can scroll it too.
    <div
      role="region"
      aria-label={caption}
      tabIndex={0}
      className="overflow-x-auto rounded-md border border-border bg-surface"
    >
      <table className="w-full min-w-[40rem] border-collapse text-left text-body">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border text-caption text-fg-subtle">
            <th scope="col" className="w-28 px-4 py-2 font-medium">
              Result
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              Check
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              Observed
            </th>
            <th scope="col" className="px-4 py-2 font-medium">
              Target
            </th>
          </tr>
        </thead>
        <tbody>
          {probes.map((probe) => (
            <tr key={probe.key} className="border-b border-border last:border-b-0">
              <td className="px-4 py-3 align-top">
                <ProbeOutcomeBadge outcome={probe.outcome} />
              </td>
              <th scope="row" className="px-4 py-3 align-top font-normal">
                <span className="block font-medium text-fg">{probe.name}</span>
                <span className="block text-label text-fg-muted">{probe.how}</span>
              </th>
              <td className="px-4 py-3 align-top font-mono text-mono text-fg tabular-nums">
                {probe.observed ?? "—"}
              </td>
              <td className="px-4 py-3 align-top font-mono text-mono text-fg-subtle tabular-nums">
                {probe.target}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
