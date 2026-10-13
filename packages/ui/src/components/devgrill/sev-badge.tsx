import { cva } from "class-variance-authority";
import { SevGlyph, type Severity } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";

const SEV_NAMES: Record<Severity, string> = {
  1: "critical",
  2: "major",
  3: "minor",
  4: "warm-up",
};

const sevBadge = cva(
  "inline-flex shrink-0 items-center gap-1.5 rounded-xs font-medium whitespace-nowrap tabular-nums",
  {
    variants: {
      sev: {
        1: "bg-sev1-bg text-sev1-fg",
        2: "bg-sev2-bg text-sev2-fg",
        3: "bg-sev3-bg text-sev3-fg",
        4: "bg-sev4-bg text-sev4-fg",
      },
      size: {
        sm: "px-1.5 py-0.5 text-caption",
        md: "px-2 py-1 text-label",
      },
    },
    defaultVariants: { size: "sm" },
  },
);

export type SevBadgeProps = {
  sev: Severity;
  /** Show the severity name ("SEV2 major") instead of just "SEV2". */
  showName?: boolean;
  size?: "sm" | "md";
  className?: string;
};

/**
 * Severity in three channels: glyph + label + colour (WCAG 1.4.1). Used for both
 * in-scenario severity and scenario difficulty (SEV4 warm-up … SEV1 hardest).
 */
export function SevBadge({ sev, showName = false, size, className }: SevBadgeProps) {
  return (
    <span className={cn(sevBadge({ sev, size }), className)}>
      <SevGlyph sev={sev} className={size === "md" ? "h-3 w-12" : undefined} />
      <span>
        SEV{sev}
        {showName ? <span className="font-normal"> {SEV_NAMES[sev]}</span> : null}
      </span>
    </span>
  );
}

export { SEV_NAMES };
