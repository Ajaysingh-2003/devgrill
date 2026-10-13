import type { Metadata } from "next";
import { Suspense, cache } from "react";
import { myStreak, publicProfile, type StreakOut } from "@devgrill/api-client";
import { Streak } from "@devgrill/ui/components/devgrill/streak";
import { PageSkeleton } from "@/components/page-skeleton";
import { Sparkline } from "@/components/sparkline";
import { api, unwrap } from "@/lib/api";
import { monthYear } from "@/lib/format";
import { getViewer } from "@/lib/viewer";

const loadProfile = cache(async (handle: string) =>
  unwrap(publicProfile({ client: await api(), path: { handle } })),
);

export async function generateMetadata({ params }: PageProps<"/u/[handle]">): Promise<Metadata> {
  const { handle } = await params;
  const profile = await loadProfile(handle);
  return { title: `${profile.display_name} (@${profile.handle})` };
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase() || "?";
}

/** Practice days in the last 12 weeks: one column per week, oldest first. */
function ActivityGrid({ streak }: { streak: StreakOut }) {
  const active = new Set(streak.days);
  const start = new Date(`${streak.window_start}T00:00:00Z`);
  const days = Array.from({ length: 84 }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i);
    return d.toISOString().slice(0, 10);
  });
  const weeks = Array.from({ length: 12 }, (_, w) => days.slice(w * 7, w * 7 + 7));
  return (
    <section aria-labelledby="activity-title" className="flex flex-col gap-3">
      <h2 id="activity-title" className="text-heading-md font-semibold text-fg">
        Last 12 weeks
      </h2>
      <div
        role="img"
        aria-label={`Practised on ${active.size} of the last 84 days; longest streak ${streak.longest} days`}
        className="flex gap-1"
      >
        {weeks.map((week) => (
          <div key={week[0]} className="flex flex-col gap-1">
            {week.map((day) => (
              <span
                key={day}
                title={day}
                className={
                  active.has(day) ? "size-3.5 rounded-[3px] bg-brand" : "size-3.5 rounded-[3px] bg-raised"
                }
              />
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

async function Profile({ params }: { params: PageProps<"/u/[handle]">["params"] }) {
  const { handle } = await params;
  const [profile, viewer] = await Promise.all([loadProfile(handle), getViewer()]);
  const isMe = viewer?.handle.toLowerCase() === profile.handle.toLowerCase();
  const streak = isMe ? (await myStreak({ client: await api() })).data : undefined;

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-wrap items-center gap-4">
        <span className="grid size-14 place-items-center overflow-hidden rounded-full bg-brand-subtle text-heading-md font-semibold text-brand-text">
          {profile.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={profile.avatar_url} alt="" width={56} height={56} className="size-14" />
          ) : (
            initials(profile.display_name)
          )}
        </span>
        <div className="flex flex-1 flex-col">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">{profile.display_name}</h1>
          <p className="text-body text-fg-muted">
            @{profile.handle}, practising since {monthYear(profile.created_at)},{" "}
            {profile.resolved === 1 ? "1 incident" : `${profile.resolved} incidents`} resolved
          </p>
        </div>
        {streak ? <Streak days={streak.current} /> : null}
      </header>

      <section aria-labelledby="ratings-title" className="flex flex-col gap-3">
        <h2 id="ratings-title" className="text-heading-md font-semibold text-fg">
          Ratings by track
        </h2>
        {profile.ratings.length ? (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {profile.ratings.map((r) => (
              <li
                key={r.track_slug}
                className="flex items-center gap-4 rounded-md border border-border bg-surface p-4"
              >
                <div className="flex flex-1 flex-col">
                  <span className="text-label text-fg-muted">{r.track_title}</span>
                  <span className="font-mono text-stat font-semibold text-fg tabular-nums">
                    {Math.round(r.rating)}
                  </span>
                </div>
                {r.history.length > 1 ? (
                  <Sparkline
                    values={r.history.map((p) => p.rating)}
                    width={96}
                    height={36}
                    label={`${r.track_title} rating over the last ${r.history.length} incidents`}
                    className="h-9 w-24"
                  />
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-body text-fg-muted">
            {isMe ? "Resolve your first incident to get a rating in that track." : "No rated incidents yet."}
          </p>
        )}
      </section>

      {streak ? <ActivityGrid streak={streak} /> : null}
    </div>
  );
}

/** T9 Profile: public ratings for anyone; your own streak and activity when it's you. */
export default function ProfilePage({ params }: PageProps<"/u/[handle]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading profile" />}>
      <Profile params={params} />
    </Suspense>
  );
}
