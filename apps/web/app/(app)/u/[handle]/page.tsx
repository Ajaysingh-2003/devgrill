import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, cache } from "react";
import { ArrowDown, ArrowUp, Settings } from "lucide-react";
import {
  getMe,
  myAttempts,
  myProgress,
  myStreak,
  myUsage,
  publicProfile,
  type AttemptSummary,
  type ExperienceLevel,
  type PublicProfile,
  type StreakOut,
  type TrackProgressDetail,
  type UsageOut,
} from "@devgrill/api-client";
import { MasteryRing } from "@devgrill/ui/components/devgrill/mastery-ring";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { StatusPill, type Status } from "@devgrill/ui/components/devgrill/status-pill";
import type { Severity } from "@devgrill/ui/icons";
import { cn } from "@devgrill/ui/lib/utils";
import { PageSkeleton } from "@/components/page-skeleton";
import { SignOutButton } from "@/components/profile/sign-out-button";
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

const EXPERIENCE: Record<ExperienceLevel, string> = {
  student: "Student",
  "0-2": "Up to 2 years in industry",
  "2-5": "2 to 5 years in industry",
  "5+": "5+ years in industry",
};

const MODES: Record<string, string> = {
  tutorial: "Tutorial",
  guided: "With hints",
  oncall: "No hints",
  daily: "Daily",
  weekly: "Weekly",
};

/** How a run ended, as a status pill (icon + label + colour). */
const OUTCOMES: Record<string, { status: Status; label: string }> = {
  resolved: { status: "resolved", label: "Solved" },
  expired: { status: "unknown", label: "Time ran out" },
  abandoned: { status: "unknown", label: "Left early" },
  failed: { status: "degraded", label: "Didn't start" },
};

const PERIOD: Record<string, string> = { day: "today", week: "this week", ever: "in total" };

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase() || "?";
}

function shortDate(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(iso));
}

/** Practice days in the last 12 weeks: one column per week, oldest first. */
function ActivityGrid({ streak, pro = false }: { streak: StreakOut; pro?: boolean }) {
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
                className={cn("size-3.5 rounded-[3px]", active.has(day) ? "bg-brand" : "bg-raised")}
              />
            ))}
          </div>
        ))}
      </div>
      <p className="text-label text-fg-muted">
        {active.size === 1 ? "1 day" : `${active.size} days`} with a finished drill
        {pro ? null : (
          <>
            . Longest streak {streak.longest === 1 ? "1 day" : `${streak.longest} days`}
            {streak.freezes
              ? `, ${streak.freezes} streak ${streak.freezes === 1 ? "freeze" : "freezes"} saved`
              : ""}
          </>
        )}
        .
      </p>
    </section>
  );
}

/** The numbers that summarise a player: one strip, read left to right. */
function Stats({ profile, streak, usage }: { profile: PublicProfile; streak?: StreakOut; usage?: UsageOut }) {
  const best = [...profile.ratings].sort((a, b) => b.rating - a.rating)[0];
  const games = profile.ratings.reduce((n, r) => n + r.games, 0);
  const cells: [string, string, string][] = [
    ["Drills solved", String(profile.resolved), games ? `${games} rated` : "none rated yet"],
    best
      ? ["Best rating", String(Math.round(best.rating)), best.track_title]
      : ["Best rating", "–", "resolve one to get rated"],
  ];
  if (streak) {
    cells.push([
      "Current streak",
      streak.current === 1 ? "1 day" : `${streak.current} days`,
      `best ${streak.longest === 1 ? "1 day" : `${streak.longest} days`}`,
    ]);
  }
  if (usage) {
    const q = usage.live_starts;
    cells.push([
      "Plays used",
      `${Math.round(q.used)} of ${q.limit}`,
      `${usage.tier} plan, ${PERIOD[q.period] ?? ""}`.trim(),
    ]);
  }
  return (
    <dl
      className={cn(
        "grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border",
        cells.length > 2 && "lg:grid-cols-4",
      )}
    >
      {cells.map(([k, v, note]) => (
        <div key={k} className="flex flex-col gap-0.5 bg-surface px-4 py-3">
          <dt className="text-label text-fg-muted">{k}</dt>
          <dd className="font-mono text-stat font-semibold text-fg tabular-nums">{v}</dd>
          <dd className="text-caption text-fg-subtle first-letter:uppercase">{note}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The player's own incident log: what they played, how it ended, what it did to the rating. */
function IncidentLog({ attempts }: { attempts: AttemptSummary[] }) {
  return (
    <section aria-labelledby="log-title" className="flex flex-col gap-3">
      <h2 id="log-title" className="text-heading-md font-semibold text-fg">
        Recent drills
      </h2>
      {attempts.length ? (
        <div className="overflow-x-auto rounded-md border border-border bg-surface">
          <table className="w-full min-w-[40rem] text-left text-body">
            <caption className="sr-only">
              Your recent drills with severity, outcome, score, rating change and date
            </caption>
            <thead className="border-b border-border text-caption text-fg-subtle">
              <tr>
                {["Drill", "Outcome", "Working again in", "Score", "Rating", "Played"].map((h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {attempts.map((a) => {
                const ended = a.ended_at != null;
                const outcome = OUTCOMES[a.state] ?? { status: "investigating" as const, label: "Live now" };
                const href = ended ? `/incident/${a.id}/debrief` : `/incident/${a.id}`;
                return (
                  <tr key={a.id} className="border-b border-border last:border-b-0 hover:bg-raised">
                    <th scope="row" className="px-3 py-2.5 font-normal">
                      <span className="flex items-center gap-2.5">
                        <SevBadge sev={Number(a.difficulty.slice(3)) as Severity} size="sm" />
                        <span className="flex min-w-0 flex-col">
                          <Link href={href} className="font-medium text-fg hover:underline">
                            {a.scenario_title}
                          </Link>
                          <span className="text-caption text-fg-subtle">{MODES[a.mode] ?? a.mode}</span>
                        </span>
                      </span>
                    </th>
                    <td className="px-3 py-2.5">
                      <StatusPill status={outcome.status} label={outcome.label} />
                    </td>
                    <td className="px-3 py-2.5 font-mono text-mono text-fg-muted tabular-nums">
                      {a.mitigation_minutes != null ? `${Math.round(a.mitigation_minutes)} min` : "–"}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-mono text-fg tabular-nums">
                      {a.score != null ? `${Math.round(a.score * 100)}` : "–"}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-mono tabular-nums">
                      <RatingChange delta={a.rating_delta} />
                    </td>
                    <td className="px-3 py-2.5 text-fg-muted">
                      <time dateTime={a.started_at}>{shortDate(a.started_at)}</time>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-body text-fg-muted">
          Nothing played yet.{" "}
          <Link href="/drills" className="font-medium text-brand-text hover:underline">
            Pick a drill
          </Link>{" "}
          to start your record.
        </p>
      )}
    </section>
  );
}

function RatingChange({ delta }: { delta: number | null | undefined }) {
  if (delta == null) return <span className="text-fg-subtle">–</span>;
  const rounded = Math.round(delta);
  if (rounded === 0) return <span className="text-fg-muted">±0</span>;
  const up = rounded > 0;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <span className={cn("inline-flex items-center gap-0.5", up ? "text-success-text" : "text-danger-text")}>
      <Icon className="size-3.5" aria-hidden="true" />
      <span className="sr-only">{up ? "up " : "down "}</span>
      {up ? `+${rounded}` : rounded}
    </span>
  );
}

/** Share of each track's published incidents resolved, with the topics underneath. */
function Mastery({ tracks }: { tracks: TrackProgressDetail[] }) {
  const played = tracks.filter((t) => t.attempted > 0 || t.solved > 0);
  return (
    <section aria-labelledby="mastery-title" className="flex flex-col gap-3">
      <h2 id="mastery-title" className="text-heading-md font-semibold text-fg">
        Track mastery
      </h2>
      {played.length ? (
        <ul className="flex flex-col gap-3">
          {played.map((t) => (
            <li key={t.track_slug} className="flex items-center gap-3">
              <MasteryRing value={t.mastery_pct} label={t.track_title} size={44} />
              <div className="flex min-w-0 flex-col">
                <Link
                  href={`/drills/${t.track_slug}`}
                  className="text-body font-medium text-fg hover:underline"
                >
                  {t.track_title}
                </Link>
                <span className="text-caption text-fg-muted">
                  {t.solved} of {t.total} solved
                  {t.attempted > t.solved ? `, ${t.attempted - t.solved} in progress` : ""}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-fg-muted">Mastery shows up once you&apos;ve played a track.</p>
      )}
    </section>
  );
}

function Ratings({ profile, isMe }: { profile: PublicProfile; isMe: boolean }) {
  return (
    <section aria-labelledby="ratings-title" className="flex flex-col gap-3">
      <h2 id="ratings-title" className="text-heading-md font-semibold text-fg">
        Ratings by track
      </h2>
      {profile.ratings.length ? (
        <ul className="grid gap-3 sm:grid-cols-2">
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
                <span className="text-caption text-fg-subtle">
                  {r.games === 1 ? "1 rated drill" : `${r.games} rated drills`}
                  {/* A high deviation means few games: the number will still move a lot. */}
                  {r.rd > 150 ? ", still settling" : ""}
                </span>
              </div>
              {r.history.length > 1 ? (
                <Sparkline
                  values={r.history.map((p) => p.rating)}
                  width={96}
                  height={36}
                  label={`${r.track_title} rating over the last ${r.history.length} drills`}
                  className="h-9 w-24"
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-fg-muted">
          {isMe ? "Solve your first drill to get a rating in that track." : "No rated drills yet."}
        </p>
      )}
    </section>
  );
}

async function Profile({ params }: { params: PageProps<"/u/[handle]">["params"] }) {
  const { handle } = await params;
  const [profile, viewer] = await Promise.all([loadProfile(handle), getViewer()]);
  const isMe = viewer?.handle.toLowerCase() === profile.handle.toLowerCase();
  // Pro mode: no streaks, just the work.
  const pro = isMe && Boolean(viewer?.prefs.pro_mode);

  let me, streak, attempts, tracks, usage;
  if (isMe) {
    const client = await api();
    [me, streak, attempts, tracks, usage] = await Promise.all([
      getMe({ client }).then((r) => r.data),
      myStreak({ client }).then((r) => r.data),
      myAttempts({ client, query: { limit: 8 } }).then((r) => r.data?.items ?? []),
      myProgress({ client }).then((r) => r.data ?? []),
      myUsage({ client }).then((r) => r.data),
    ]);
  }
  const about = [
    me?.experience_level ? EXPERIENCE[me.experience_level] : null,
    me?.country ? new Intl.DisplayNames(["en"], { type: "region" }).of(me.country) : null,
  ].filter(Boolean);

  return (
    <div className="flex flex-col gap-10">
      <header className="flex flex-wrap items-center gap-4">
        <span className="grid size-16 place-items-center overflow-hidden rounded-full bg-brand-subtle text-heading-md font-semibold text-brand-text">
          {profile.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={profile.avatar_url} alt="" width={64} height={64} className="size-16" />
          ) : (
            initials(profile.display_name)
          )}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">{profile.display_name}</h1>
          <p className="text-body text-fg-muted">
            @{profile.handle}, practising since {monthYear(profile.created_at)}
          </p>
          {about.length ? <p className="text-label text-fg-subtle">{about.join(", ")}</p> : null}
        </div>
        {isMe ? (
          <div className="flex items-center gap-2">
            <Link
              href="/settings"
              className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-border-input px-3 text-label font-medium text-fg hover:bg-raised"
            >
              <Settings className="size-4" aria-hidden="true" />
              Settings
            </Link>
            <SignOutButton />
          </div>
        ) : null}
      </header>

      <Stats profile={profile} streak={pro ? undefined : (streak ?? undefined)} usage={usage ?? undefined} />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-10">
          {attempts ? <IncidentLog attempts={attempts} /> : null}
          <Ratings profile={profile} isMe={isMe} />
        </div>
        {isMe ? (
          <aside aria-label="Progress" className="flex flex-col gap-10">
            {tracks ? <Mastery tracks={tracks} /> : null}
            {streak ? <ActivityGrid streak={streak} pro={pro} /> : null}
          </aside>
        ) : null}
      </div>
      {isMe ? (
        <p className="text-label text-fg-subtle">
          Others see your name, ratings and drills solved. Your recent drills, mastery, streak and plan are
          only shown to you.
        </p>
      ) : null}
    </div>
  );
}

/** T9 Profile: public ratings for anyone; your own log, mastery, streak and plan when it's you. */
export default function ProfilePage({ params }: PageProps<"/u/[handle]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading profile" />}>
      <Profile params={params} />
    </Suspense>
  );
}
