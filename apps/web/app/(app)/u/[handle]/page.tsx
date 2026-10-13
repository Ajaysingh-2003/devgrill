import type { Metadata } from "next";
import { Suspense } from "react";
import { Streak } from "@devgrill/ui/components/devgrill/streak";
import { PageSkeleton } from "@/components/page-skeleton";
import { Sparkline } from "@/components/sparkline";
import { PROFILE } from "@/lib/mock";

export const metadata: Metadata = { title: "Profile" };

export function generateStaticParams() {
  return [{ handle: PROFILE.handle }];
}

const LEVEL_FILL = [
  "var(--raised)",
  "oklch(from var(--brand) l c h / 0.35)",
  "oklch(from var(--brand) l c h / 0.65)",
  "var(--brand)",
];

async function Profile({ params }: { params: PageProps<"/u/[handle]">["params"] }) {
  const { handle } = await params;
  const weeks = Array.from({ length: 12 }, (_, w) => PROFILE.activity.slice(w * 7, w * 7 + 7));
  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-wrap items-center gap-4">
        <span className="grid size-14 place-items-center rounded-full bg-brand-subtle text-heading-md font-semibold text-brand-text">
          AS
        </span>
        <div className="flex flex-1 flex-col">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">{PROFILE.name}</h1>
          <p className="text-body text-fg-muted">
            @{handle}, practising since {PROFILE.joined}, {PROFILE.resolved} incidents resolved
          </p>
        </div>
        <Streak days={PROFILE.streakDays} />
      </header>

      <section aria-labelledby="ratings-title" className="flex flex-col gap-3">
        <h2 id="ratings-title" className="text-heading-md font-semibold text-fg">
          Ratings by track
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PROFILE.ratings.map((r) => (
            <li
              key={r.track}
              className="flex items-center gap-4 rounded-md border border-border bg-surface p-4"
            >
              <div className="flex flex-1 flex-col">
                <span className="text-label text-fg-muted">{r.track}</span>
                <span className="font-mono text-stat font-semibold text-fg tabular-nums">{r.rating}</span>
              </div>
              <Sparkline
                values={r.history}
                width={96}
                height={36}
                label={`${r.track} rating over the last six incidents`}
                className="h-9 w-24"
              />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="activity-title" className="flex flex-col gap-3">
        <h2 id="activity-title" className="text-heading-md font-semibold text-fg">
          Last 12 weeks
        </h2>
        <div
          role="img"
          aria-label="Activity over the last 12 weeks: practised on most weekdays"
          className="flex gap-1"
        >
          {weeks.map((week, w) => (
            <div key={w} className="flex flex-col gap-1">
              {week.map((level, d) => (
                <span key={d} className="size-3.5 rounded-[3px]" style={{ background: LEVEL_FILL[level] }} />
              ))}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/** T9 Profile. */
export default function ProfilePage({ params }: PageProps<"/u/[handle]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading profile" />}>
      <Profile params={params} />
    </Suspense>
  );
}
