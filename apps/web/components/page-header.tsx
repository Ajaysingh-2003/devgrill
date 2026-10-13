import type { ReactNode } from "react";
import { cn } from "@devgrill/ui/lib/utils";

/** Control-room page header: plain title, one line of context, optional actions. No eyebrow labels. */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="flex max-w-2xl flex-col gap-1.5">
        <h1 className="text-heading-lg font-semibold tracking-tight text-fg">{title}</h1>
        {description ? <p className="text-body-lg text-fg-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
