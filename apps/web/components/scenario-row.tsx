import Link from "next/link";
import { CircleCheck, CircleDashed, CircleDot } from "lucide-react";
import type { ScenarioCard } from "@devgrill/api-client";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { sevNumber } from "@/lib/format";

export const STATUS = {
  solved: { label: "Solved", icon: CircleCheck, tone: "text-success-text" },
  attempted: { label: "Not solved yet", icon: CircleDot, tone: "text-warning-text" },
  new: { label: "Not started", icon: CircleDashed, tone: "text-fg-subtle" },
} as const;

/** One drill in a list: severity, title and summary, length, and the caller's progress. */
export function ScenarioRow({ s, showTrack = false }: { s: ScenarioCard; showTrack?: boolean }) {
  const st = s.progress ? STATUS[s.progress] : null;
  return (
    <li>
      <Link
        href={`/drills/${s.track_slug}/${s.slug}`}
        transitionTypes={["nav-forward"]}
        className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-1 rounded-sm px-3 py-3 hover:bg-raised md:grid-cols-[6rem_1fr_7rem_8rem]"
      >
        <SevBadge sev={sevNumber(s.difficulty)} />
        <span className="flex min-w-0 flex-col">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-body font-semibold text-fg">{s.title}</span>
            {s.playable === false ? (
              <span className="rounded-xs bg-raised px-1.5 py-0.5 text-caption text-fg-muted">
                Coming soon
              </span>
            ) : s.access === "pro" ? (
              <span className="rounded-xs border border-border px-1.5 py-0.5 text-caption text-fg-muted">
                Pro
              </span>
            ) : null}
          </span>
          <span className="truncate text-label text-fg-muted">
            {showTrack && s.topic_title ? `${s.topic_title}: ` : null}
            {s.summary}
          </span>
        </span>
        <span className="col-start-2 font-mono text-mono-sm text-fg-muted md:col-start-auto">
          about {s.est_minutes} min
        </span>
        {st ? (
          <span
            className={`col-start-2 inline-flex items-center gap-1.5 text-label md:col-start-auto ${st.tone}`}
          >
            <st.icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
            {st.label}
          </span>
        ) : null}
      </Link>
    </li>
  );
}
