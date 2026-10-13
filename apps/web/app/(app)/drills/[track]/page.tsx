import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { PageSkeleton } from "@/components/page-skeleton";
import { PageTransition } from "@/components/page-transition";
import { notFound } from "next/navigation";
import { CircleCheck, CircleDashed, CircleDot } from "lucide-react";
import { MasteryRing } from "@devgrill/ui/components/devgrill/mastery-ring";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ServiceIcon } from "@devgrill/ui/icons";
import { SCENARIOS, TRACKS, track, type ScenarioStatus } from "@/lib/mock";

export function generateStaticParams() {
  return TRACKS.map((t) => ({ track: t.slug }));
}

export async function generateMetadata({ params }: PageProps<"/drills/[track]">): Promise<Metadata> {
  const { track: slug } = await params;
  return { title: track(slug)?.name ?? "Track" };
}

const STATUS: Record<ScenarioStatus, { label: string; icon: typeof CircleCheck; tone: string }> = {
  solved: { label: "Solved", icon: CircleCheck, tone: "text-success-text" },
  attempted: { label: "Attempted", icon: CircleDot, tone: "text-warning-text" },
  new: { label: "Not started", icon: CircleDashed, tone: "text-fg-subtle" },
};

async function TrackContent({ params }: { params: PageProps<"/drills/[track]">["params"] }) {
  const { track: slug } = await params;
  const t = track(slug);
  if (!t) notFound();
  const scenarios = SCENARIOS.filter((s) => s.track === t.slug);
  const pct = Math.round((t.solved / t.total) * 100);

  return (
    <div className="flex flex-col gap-10">
      <nav aria-label="Breadcrumb" className="text-label text-fg-muted">
        <Link href="/drills" transitionTypes={["nav-back"]} className="hover:text-fg">
          Drills
        </Link>
        <span aria-hidden="true" className="px-1.5 text-fg-subtle">
          /
        </span>
        <span aria-current="page" className="text-fg">
          {t.name}
        </span>
      </nav>

      <header className="flex flex-wrap items-center gap-5">
        <span className="grid size-12 place-items-center rounded-md bg-raised text-brand-text">
          <ServiceIcon kind={t.service} className="size-6" />
        </span>
        <div className="flex flex-1 flex-col gap-1">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">{t.name}</h1>
          <p className="max-w-2xl text-body-lg text-fg-muted">{t.summary}</p>
        </div>
        <div className="flex items-center gap-3">
          <MasteryRing value={pct} label={t.name} size={56} />
          <div className="flex flex-col">
            <span className="font-mono text-stat font-semibold text-fg">{t.rating}</span>
            <span className="text-caption text-fg-muted">track rating</span>
          </div>
        </div>
      </header>

      {t.topics.map((topic) => {
        const items = scenarios.filter((s) => s.topic === topic);
        return (
          <section key={topic} aria-labelledby={`topic-${topic}`} className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between gap-4 border-b border-border pb-2">
              <h2 id={`topic-${topic}`} className="text-heading-md font-semibold text-fg">
                {topic}
              </h2>
              <Link href="#" className="text-label font-medium text-brand-text hover:underline">
                Read the 4-minute primer
              </Link>
            </div>
            {items.length ? (
              <ul className="flex flex-col">
                {items.map((s) => {
                  const st = STATUS[s.status];
                  return (
                    <li key={s.slug}>
                      <Link
                        href={`/drills/${t.slug}/${s.slug}`}
                        transitionTypes={["nav-forward"]}
                        className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-1 rounded-sm px-3 py-3 hover:bg-raised md:grid-cols-[6rem_1fr_6rem_7rem_8rem]"
                      >
                        <SevBadge sev={s.sev} />
                        <span className="flex min-w-0 flex-col">
                          <span className="text-body font-semibold text-fg">{s.title}</span>
                          <span className="truncate text-label text-fg-muted">{s.symptom}</span>
                        </span>
                        <span className="col-start-2 font-mono text-mono-sm text-fg-muted md:col-start-auto">
                          about {s.minutes} min
                        </span>
                        <span className="col-start-2 font-mono text-mono-sm text-fg-muted md:col-start-auto">
                          {s.solveRate}% solve rate
                        </span>
                        <span
                          className={`col-start-2 inline-flex items-center gap-1.5 text-label md:col-start-auto ${st.tone}`}
                        >
                          <st.icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
                          {st.label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="px-3 text-body text-fg-muted">
                Scenarios for this topic arrive with the next content release.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}

export default function TrackPage({ params }: PageProps<"/drills/[track]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading track" />}>
      <PageTransition>
        <TrackContent params={params} />
      </PageTransition>
    </Suspense>
  );
}
