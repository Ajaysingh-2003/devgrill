import {
  CircleCheck,
  CircleDashed,
  CircleDot,
  OctagonAlert,
  Search,
  ShieldCheck,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

export type Status =
  "firing" | "degraded" | "investigating" | "mitigated" | "resolved" | "healthy" | "unknown";

const STATUS: Record<Status, { label: string; icon: LucideIcon; tone: string }> = {
  firing: { label: "Firing", icon: OctagonAlert, tone: "bg-danger-subtle text-danger-text" },
  degraded: { label: "Degraded", icon: TriangleAlert, tone: "bg-warning-subtle text-warning-text" },
  investigating: { label: "Investigating", icon: Search, tone: "bg-info-subtle text-info-text" },
  mitigated: { label: "Mitigated", icon: ShieldCheck, tone: "bg-brand-subtle text-brand-text" },
  resolved: { label: "Resolved", icon: CircleCheck, tone: "bg-success-subtle text-success-text" },
  healthy: { label: "Healthy", icon: CircleDot, tone: "bg-success-subtle text-success-text" },
  unknown: { label: "Unknown", icon: CircleDashed, tone: "bg-raised text-fg-muted" },
};

export function StatusPill({
  status,
  label,
  className,
}: {
  status: Status;
  /** Override the default label, e.g. "Mitigated at 08:12". */
  label?: string;
  className?: string;
}) {
  const { icon: Icon, tone, label: fallback } = STATUS[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-caption font-medium whitespace-nowrap",
        tone,
        className,
      )}
    >
      <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />
      {label ?? fallback}
    </span>
  );
}
