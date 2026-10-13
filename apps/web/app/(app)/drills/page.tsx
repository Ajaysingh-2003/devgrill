import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { dailyChallenge, listTracks, myAttempts, type AttemptSummary } from "@devgrill/api-client";
import { MasteryRing } from "@devgrill/ui/components/devgrill/mastery-ring";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ServiceIcon } from "@devgrill/ui/icons";
import { PageHeader } from "@/components/page-header";
import { PageSkeleton } from "@/components/page-skeleton";
import { PageTransition } from "@/components/page-transition";
import { api, sevNumber, unwrap } from "@/lib/api";
import { formatCount, timeLeft } from "@/lib/format";

export const metadata: Metadata = { title: "Drills" };

async function DailyCard() {
  const client = await api();
  const { data: daily } = await dailyChallenge({ client });
  if (!daily) return null; // no published scenarios yet: nothing to feature
  const s = daily.scenario;
  return (
    <section
      aria-labelledby="daily-title"
      className="grid gap-4 rounded-md border border-border bg-surface p-5 sm:grid-cols-[1fr_auto] sm:items-center"
    >
      <div className="flex flex-col gap-2">
        <h2 id="daily-title" className="text-label font-medium text-fg-muted">
          Today’s incident, same for everyone, closes in {timeLeft(daily.ends_at)}
        </h2>
        <p className="flex flex-wrap items-center gap-3">
          <SevBadge sev={sevNumber(s.difficulty)} />
          <span className="text-heading-md font-semibold text-fg">{s.title}</span>
        </p>
        <p className="text-body text-fg-muted">
          {s.summary}.{" "}
          {daily.players
            ? `${formatCount(daily.players)} engineers have played it.`
            : "Be the first to play it today."}
        </p>
      </div>
      <Link
        href={`/drills/${s.track_slug}/${s.slug}`}
        transitionTypes={["nav-forward"]}
        className="inline-flex h-9 items-center justify-center rounded-sm bg-brand px-4 text-label font-semibold text-on-brand hover:bg-brand-hover"
      >
        Take today’s incident
      </Link>
    </section>
  );
}

async function SystemMap() {
  const client = await api();
  const tracks = await unwrap(listTracks({ client }));
  const signedIn = tracks.some((t) => t.progress);
  return (
    <section aria-labelledby="map-title" className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="map-title" className="text-heading-md font-semibold text-fg">
          {signedIn ? "Your system map" : "The system map"}
        </h2>
        <p className="text-label text-fg-subtle">
          {signedIn
            ? "Rings show how much of each track you have solved."
            : "Sign in to track your progress."}
        </p>
      </div>
      <ul
        className="grid gap-5 rounded-lg border border-border p-5 sm:grid-cols-2 lg:grid-cols-3"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, var(--border-strong) 1px, transparent 0)",
          backgroundSize: "16px 16px",
        }}
      >
        {tracks.map((t) => (
          <li key={t.slug}>
            <Link
              href={`/drills/${t.slug}`}
              transitionTypes={["nav-forward"]}
              className="group flex h-full flex-col gap-3 rounded-md border border-border bg-surface p-4 transition-colors duration-[var(--duration-fast)] hover:border-border-strong"
            >
              <span className="flex items-start gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-sm bg-raised text-fg-muted group-hover:text-brand-text">
                  <ServiceIcon kind={t.icon} className="size-[1.125rem]" />
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-body-lg font-semibold text-fg">{t.title}</span>
                  <span className="text-label text-fg-muted">
                    {t.scenario_count === 0
                      ? "Scenarios coming soon"
                      : t.progress
                        ? `${t.progress.solved} of ${t.scenario_count} solved${
                            t.progress.rating ? `, rating ${Math.round(t.progress.rating)}` : ""
                          }`
                        : `${t.scenario_count} scenario${t.scenario_count === 1 ? "" : "s"}`}
                  </span>
                </span>
                {t.progress && t.scenario_count > 0 ? (
                  <MasteryRing value={t.progress.mastery_pct} label={t.title} />
                ) : null}
              </span>
              <span className="text-body text-fg-muted">{t.summary}</span>
              <span className="mt-auto flex flex-wrap gap-1.5">
                {t.topics.map((topic) => (
                  <span key={topic} className="rounded-xs bg-raised px-1.5 py-0.5 text-caption text-fg-muted">
                    {topic}
                  </span>
                ))}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Scenarios the user tried but hasn't resolved yet (newest first, one row per scenario). */
async function ContinueList() {
  const client = await api();
  const { data } = await myAttempts({ client, query: { limit: 50 } });
  if (!data) return null; // signed out
  const latest = new Map<string, AttemptSummary>();
  const resolved = new Set<string>();
  for (const a of data.items) {
    if (a.state === "resolved") resolved.add(a.scenario_slug);
    if (!latest.has(a.scenario_slug)) latest.set(a.scenario_slug, a);
  }
  const open = [...latest.values()].filter((a) => !resolved.has(a.scenario_slug)).slice(0, 5);
  if (!open.length) return null;
  return (
    <section aria-labelledby="continue-title" className="flex flex-col gap-3">
      <h2 id="continue-title" className="text-heading-md font-semibold text-fg">
        Pick up where you left off
      </h2>
      <ul className="divide-y divide-border rounded-md border border-border bg-surface">
        {open.map((a) => (
          <li key={a.scenario_slug}>
            <Link
              href={`/drills/${a.track_slug}/${a.scenario_slug}`}
              transitionTypes={["nav-forward"]}
              className="flex items-center gap-4 px-4 py-3 hover:bg-raised"
            >
              <SevBadge sev={sevNumber(a.difficulty)} />
              <span className="flex-1 text-body font-medium text-fg">{a.scenario_title}</span>
              <span className="text-label text-fg-muted">Attempted</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function DrillsPage() {
  return (
    <PageTransition>
      <div className="flex flex-col gap-10">
        <PageHeader
          title="Drills"
          description="Pick a system and break it on purpose. Each track goes from SEV4 warm-ups to SEV1 outages."
        />
        <Suspense fallback={<div className="h-32 rounded-md border border-border bg-surface" />}>
          <DailyCard />
        </Suspense>
        <Suspense fallback={<PageSkeleton label="Loading tracks" />}>
          <SystemMap />
        </Suspense>
        <Suspense fallback={null}>
          <ContinueList />
        </Suspense>
      </div>
    </PageTransition>
  );
}
