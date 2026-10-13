import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ProbeTable } from "@devgrill/ui/components/devgrill/probe-table";
import { VerifyCelebration } from "@devgrill/ui/components/devgrill/verify-celebration";
import { cn } from "@devgrill/ui/lib/utils";
import { ApproachExplorer } from "@/components/approach-explorer";
import { IncidentPageHeader } from "@/components/incident-page-header";
import { PROBES, REPLAY, RUBRIC, SCENARIOS } from "@/lib/mock";

export const metadata: Metadata = { title: "Debrief" };

export function generateStaticParams() {
  return [{ attemptId: "inc-4021" }];
}

async function Debrief({ params }: { params: PageProps<"/incident/[attemptId]/debrief">["params"] }) {
  const { attemptId } = await params;
  const next = SCENARIOS.filter(
    (s) => s.track === "caching" && s.status === "new" && s.slug !== "big-sale-meltdown",
  ).slice(0, 2);
  return (
    <>
      <IncidentPageHeader
        context="The Big Sale Meltdown, incident 4021"
        back={{ href: `/incident/${attemptId}`, label: "Back to the workspace" }}
      />
      <main id="main" className="mx-auto flex max-w-[72rem] flex-col gap-12 px-4 py-10 sm:px-6">
        <VerifyCelebration
          title="Your fix survived the replay"
          delta={52}
          rating={1392}
          track="Caching"
          masteryBefore={36}
          masteryAfter={45}
        />

        <dl className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4">
          {[
            ["Mitigated in", "8m 12s", "faster than 71% of players"],
            ["Resolved in", "17m 40s", "par is 25 minutes"],
            ["Hints used", "0", "full rating credit"],
            ["Postmortem", "8.5 / 10", "reviewed against the rubric"],
          ].map(([k, v, note]) => (
            <div key={k} className="flex flex-col gap-0.5 bg-surface px-4 py-3">
              <dt className="text-label text-fg-muted">{k}</dt>
              <dd className="font-mono text-stat font-semibold text-fg tabular-nums">{v}</dd>
              <dd className="text-caption text-fg-subtle">{note}</dd>
            </div>
          ))}
        </dl>

        <section aria-labelledby="probes-title" className="flex flex-col gap-3">
          <h2 id="probes-title" className="text-heading-lg font-semibold tracking-tight text-fg">
            What verify threw at your fix
          </h2>
          <p className="max-w-2xl text-body-lg text-fg-muted">
            Each probe checks a behaviour. Any implementation that holds all six passes.
          </p>
          <ProbeTable probes={PROBES} caption="Verify probes and results" />
        </section>

        <section aria-labelledby="approaches-title" className="flex flex-col gap-3">
          <h2 id="approaches-title" className="text-heading-lg font-semibold tracking-tight text-fg">
            Your fix next to everyone else’s
          </h2>
          <ApproachExplorer />
        </section>

        <div className="grid gap-8 lg:grid-cols-2">
          <section aria-labelledby="rubric-title" className="flex flex-col gap-3">
            <h2 id="rubric-title" className="text-heading-md font-semibold text-fg">
              Postmortem review
            </h2>
            <ul className="divide-y divide-border rounded-md border border-border bg-surface">
              {RUBRIC.map((r) => (
                <li key={r.item} className="flex flex-col gap-1 px-4 py-3">
                  <span className="flex justify-between gap-4">
                    <span className="text-body font-semibold text-fg">{r.item}</span>
                    <span className="font-mono text-mono text-fg-muted">{r.score}</span>
                  </span>
                  <span className="text-body text-fg-muted">{r.note}</span>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="replay-title" className="flex flex-col gap-3">
            <h2 id="replay-title" className="text-heading-md font-semibold text-fg">
              How your investigation went
            </h2>
            <ol className="flex flex-col rounded-md border border-border bg-surface">
              {REPLAY.map((e) => (
                <li
                  key={e.at}
                  className="grid grid-cols-[3.5rem_1fr_auto] items-start gap-3 border-b border-border px-4 py-2.5 last:border-b-0"
                >
                  <time className="font-mono text-mono-sm text-fg-subtle">{e.at}</time>
                  <span className="text-body text-fg">{e.text}</span>
                  {e.mark ? (
                    <span
                      className={cn(
                        "rounded-xs px-1.5 py-0.5 text-caption font-medium",
                        e.mark === "lost"
                          ? "bg-warning-subtle text-warning-text"
                          : "bg-info-subtle text-info-text",
                      )}
                    >
                      {e.mark === "lost" ? "Lost time" : "Key clue"}
                    </span>
                  ) : (
                    <span />
                  )}
                </li>
              ))}
            </ol>
            <p className="text-body text-fg-muted">
              The cache hit rate already showed 3% at 01:12. Next time, ask what changed before you touch the
              database.
            </p>
          </section>
        </div>

        <section
          aria-labelledby="next-title"
          className="flex flex-wrap items-center gap-3 border-t border-border pt-6"
        >
          <h2 id="next-title" className="text-body font-semibold text-fg">
            Next in Caching
          </h2>
          {next.map((s) => (
            <Link
              key={s.slug}
              href={`/drills/${s.track}/${s.slug}`}
              className="rounded-sm border border-border px-3 py-2 text-body text-fg hover:bg-raised"
            >
              {s.title}
            </Link>
          ))}
          <Link
            href={`/incident/${attemptId}/postmortem`}
            className="ml-auto text-body font-medium text-brand-text hover:underline"
          >
            Edit your postmortem
          </Link>
        </section>
      </main>
    </>
  );
}

/** T6 Debrief: Field Manual layer plus the one celebration moment. */
export default function DebriefPage({ params }: PageProps<"/incident/[attemptId]/debrief">) {
  return (
    <Suspense fallback={<p className="p-6 text-body text-fg-muted">Loading your debrief…</p>}>
      <Debrief params={params} />
    </Suspense>
  );
}
