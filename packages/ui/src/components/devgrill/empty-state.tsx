import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * Says why something is empty and what to do next (never a bare "No data").
 * `compact` for panels inside the workspace, default for whole pages.
 */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  compact = false,
  className,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col",
        compact ? "items-start gap-2 p-4" : "items-center gap-3 px-6 py-12 text-center",
        className,
      )}
    >
      <span
        className={cn(
          "grid place-items-center rounded-md bg-raised text-fg-muted",
          compact ? "size-8" : "size-11",
        )}
      >
        <Icon className={compact ? "size-4" : "size-5"} strokeWidth={1.75} aria-hidden="true" />
      </span>
      <div className={cn("flex flex-col gap-1", !compact && "max-w-sm")}>
        <p className={cn("font-semibold text-fg", compact ? "text-body" : "text-heading-md")}>{title}</p>
        {children ? <div className="text-body text-fg-muted">{children}</div> : null}
      </div>
      {action ? <div className={compact ? "pt-1" : "pt-2"}>{action}</div> : null}
    </div>
  );
}
