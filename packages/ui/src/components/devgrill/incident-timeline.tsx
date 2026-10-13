import {
  BellRing,
  GitCommitHorizontal,
  Lightbulb,
  MessageSquare,
  RotateCcw,
  SquareTerminal,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@devgrill/ui/lib/utils";

export type TimelineKind = "alert" | "beat" | "action" | "deploy" | "rollback" | "hint";

export type TimelineEvent = {
  id: string;
  /** Elapsed time since the page, e.g. "08:12". */
  at: string;
  kind: TimelineKind;
  text: string;
  actor?: string;
};

const KIND: Record<TimelineKind, { icon: LucideIcon; label: string; tone: string }> = {
  alert: { icon: BellRing, label: "Alert", tone: "text-danger-text" },
  beat: { icon: MessageSquare, label: "Teammate", tone: "text-info-text" },
  action: { icon: SquareTerminal, label: "You", tone: "text-fg-muted" },
  deploy: { icon: GitCommitHorizontal, label: "Deploy", tone: "text-fg-muted" },
  rollback: { icon: RotateCcw, label: "Rollback", tone: "text-warning-text" },
  hint: { icon: Lightbulb, label: "Hint", tone: "text-brand-text" },
};

/**
 * In-world events (alerts, teammate beats, your actions). These never become toasts.
 * Streaming surface, so new events appear without animation; the list itself is not a live
 * region (the workspace announces only genuine pages).
 */
export function IncidentTimeline({
  events,
  className,
  label = "Incident timeline",
}: {
  events: TimelineEvent[];
  className?: string;
  label?: string;
}) {
  return (
    <ol aria-label={label} className={cn("flex flex-col", className)}>
      {events.map((event) => {
        const { icon: Icon, label: kindLabel, tone } = KIND[event.kind];
        return (
          <li
            key={event.id}
            className="grid grid-cols-[3rem_1rem_1fr] items-start gap-x-2 border-b border-border px-3 py-2 last:border-b-0"
          >
            <time className="pt-px font-mono text-mono-sm text-fg-subtle tabular-nums">{event.at}</time>
            <Icon className={cn("mt-0.5 size-4", tone)} strokeWidth={1.75} aria-hidden="true" />
            <p className="text-body text-fg">
              <span className="sr-only">{kindLabel}: </span>
              {event.actor ? <span className="font-medium">{event.actor} </span> : null}
              <span className={event.actor ? "text-fg-muted" : undefined}>{event.text}</span>
            </p>
          </li>
        );
      })}
    </ol>
  );
}
