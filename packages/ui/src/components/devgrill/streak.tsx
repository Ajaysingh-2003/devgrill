import { Flame, Snowflake } from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * Streak counter (Arcade layer: flare colour + display face). Never shown during an
 * incident or on the debrief (docs/PLAN.md §8.5). `frozen` = a freeze is covering today.
 */
export function Streak({
  days,
  unit = "day",
  frozen = false,
  className,
}: {
  days: number;
  unit?: "day" | "week";
  frozen?: boolean;
  className?: string;
}) {
  const Icon = frozen ? Snowflake : Flame;
  const label = `${days} ${unit}${days === 1 ? "" : "s"} streak${frozen ? ", freeze active today" : ""}`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
        frozen ? "bg-info-subtle text-info-text" : "bg-raised text-flare-text",
        className,
      )}
    >
      <span className="sr-only">{label}</span>
      <Icon className="size-4" strokeWidth={2} aria-hidden="true" />
      <span aria-hidden="true" className="font-display text-label font-bold tabular-nums">
        {days}
      </span>
    </span>
  );
}
