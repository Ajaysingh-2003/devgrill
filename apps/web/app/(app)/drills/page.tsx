import type { Metadata } from "next";
import Link from "next/link";
import { MasteryRing } from "@devgrill/ui/components/devgrill/mastery-ring";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ServiceIcon } from "@devgrill/ui/icons";
import { PageHeader } from "@/components/page-header";
import { PageTransition } from "@/components/page-transition";
import { DAILY, SCENARIOS, TRACKS, scenario } from "@/lib/mock";

export const metadata: Metadata = { title: "Drills" };

export default function DrillsPage() {
  const daily = scenario(DAILY.scenario)!;
  const inProgress = SCENARIOS.filter((s) => s.status === "attempted");

  return (
    <PageTransition>
      <div className="flex flex-col gap-10">
        <PageHeader
          title="Drills"
          description="Pick a system and break it on purpose. Each track goes from SEV4 warm-ups to SEV1 outages."
        />

        <section
          aria-labelledby="daily-title"
          className="grid gap-4 rounded-md border border-border bg-surface p-5 sm:grid-cols-[1fr_auto] sm:items-center"
        >
          <div className="flex flex-col gap-2">
            <h2 id="daily-title" className="text-label font-medium text-fg-muted">
              Today’s incident, same for everyone, closes in {DAILY.closesIn}
            </h2>
            <p className="flex flex-wrap items-center gap-3">
              <SevBadge sev={daily.sev} />
              <span className="text-heading-md font-semibold text-fg">{daily.title}</span>
            </p>
            <p className="text-body text-fg-muted">
              {daily.symptom}. {DAILY.players.toLocaleString("en-IN")} engineers have played it; median time{" "}
              {DAILY.medianMinutes} minutes.
            </p>
          </div>
          <Link
            href={`/drills/${daily.track}/${daily.slug}`}
            transitionTypes={["nav-forward"]}
            className="inline-flex h-9 items-center justify-center rounded-sm bg-brand px-4 text-label font-semibold text-on-brand hover:bg-brand-hover"
          >
            Take today’s incident
          </Link>
        </section>

        <section aria-labelledby="map-title" className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-4">
            <h2 id="map-title" className="text-heading-md font-semibold text-fg">
              Your system map
            </h2>
            <p className="text-label text-fg-subtle">Rings show how much of each track you have solved.</p>
          </div>
          <ul
            className="grid gap-5 rounded-lg border border-border p-5 sm:grid-cols-2 lg:grid-cols-3"
            style={{
              backgroundImage: "radial-gradient(circle at 1px 1px, var(--border-strong) 1px, transparent 0)",
              backgroundSize: "16px 16px",
            }}
          >
            {TRACKS.map((t) => {
              const pct = Math.round((t.solved / t.total) * 100);
              return (
                <li key={t.slug}>
                  <Link
                    href={`/drills/${t.slug}`}
                    transitionTypes={["nav-forward"]}
                    className="group flex h-full flex-col gap-3 rounded-md border border-border bg-surface p-4 transition-colors duration-[var(--duration-fast)] hover:border-border-strong"
                  >
                    <span className="flex items-start gap-3">
                      <span className="grid size-9 shrink-0 place-items-center rounded-sm bg-raised text-fg-muted group-hover:text-brand-text">
                        <ServiceIcon kind={t.service} className="size-[1.125rem]" />
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="text-body-lg font-semibold text-fg">{t.name}</span>
                        <span className="text-label text-fg-muted">
                          {t.solved} of {t.total} solved, rating {t.rating}
                        </span>
                      </span>
                      <MasteryRing value={pct} label={t.name} />
                    </span>
                    <span className="text-body text-fg-muted">{t.summary}</span>
                    <span className="mt-auto flex flex-wrap gap-1.5">
                      {t.topics.map((topic) => (
                        <span
                          key={topic}
                          className="rounded-xs bg-raised px-1.5 py-0.5 text-caption text-fg-muted"
                        >
                          {topic}
                        </span>
                      ))}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>

        {inProgress.length ? (
          <section aria-labelledby="continue-title" className="flex flex-col gap-3">
            <h2 id="continue-title" className="text-heading-md font-semibold text-fg">
              Pick up where you left off
            </h2>
            <ul className="divide-y divide-border rounded-md border border-border bg-surface">
              {inProgress.map((s) => (
                <li key={s.slug}>
                  <Link
                    href={`/drills/${s.track}/${s.slug}`}
                    transitionTypes={["nav-forward"]}
                    className="flex items-center gap-4 px-4 py-3 hover:bg-raised"
                  >
                    <SevBadge sev={s.sev} />
                    <span className="flex-1 text-body font-medium text-fg">{s.title}</span>
                    <span className="text-label text-fg-muted">Attempted</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </PageTransition>
  );
}
