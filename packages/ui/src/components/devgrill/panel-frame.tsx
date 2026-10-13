import type { ReactNode } from "react";
import { cn } from "@devgrill/ui/lib/utils";

/**
 * Chrome for a workspace panel: a real heading (screen readers navigate by heading),
 * optional meta and actions, and a scrollable body.
 */
export function PanelFrame({
  title,
  meta,
  actions,
  children,
  className,
  bodyClassName,
  headingLevel = 2,
  id,
  tab,
}: {
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  headingLevel?: 2 | 3;
  id?: string;
  /** Id of the tab that controls this panel: renders it as that tab's tabpanel. */
  tab?: string;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const headingId = id ? `${id}-title` : undefined;
  return (
    // The labelled region is the scrollable body (one landmark per panel, not two).
    <section
      id={id}
      role={tab ? "tabpanel" : undefined}
      aria-labelledby={tab}
      className={cn("flex h-full min-h-0 flex-col bg-surface", className)}
    >
      <header className="flex h-10 shrink-0 items-center gap-3 border-b border-border px-3">
        <Heading id={headingId} className="text-label font-semibold text-fg">
          {title}
        </Heading>
        {meta ? <div className="min-w-0 truncate text-caption text-fg-subtle">{meta}</div> : null}
        {actions ? <div className="ml-auto flex items-center gap-1">{actions}</div> : null}
      </header>
      {/* Scrollable body is keyboard-focusable so it can be scrolled (and maximised with F). */}
      <div
        role="region"
        tabIndex={0}
        aria-labelledby={headingId}
        aria-label={headingId ? undefined : title}
        className={cn(
          "min-h-0 flex-1 overflow-auto outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-inset",
          bodyClassName,
        )}
      >
        {children}
      </div>
    </section>
  );
}
