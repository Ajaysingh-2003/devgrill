import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, cache } from "react";
import { CircleCheck, CircleDashed, CircleDot } from "lucide-react";
import { getTrack, type ScenarioCard } from "@devgrill/api-client";
import { MasteryRing } from "@devgrill/ui/components/devgrill/mastery-ring";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ServiceIcon } from "@devgrill/ui/icons";
import { PageSkeleton } from "@/components/page-skeleton";
import { PageTransition } from "@/components/page-transition";
import { api, sevNumber, unwrap } from "@/lib/api";

const loadTrack = cache(async (slug: string) => unwrap(getTrack({ client: await api(), path: { slug } })));

export async function generateMetadata({ params }: PageProps<"/drills/[track]">): Promise<Metadata> {
  const { track: slug } = await params;
  return { title: (await loadTrack(slug)).title };
}

const STATUS = {
  solved: { label: "Solved", icon: CircleCheck, tone: "text-success-text" },
  attempted: { label: "Not solved yet", icon: CircleDot, tone: "text-warning-text" },
  new: { label: "Not started", icon: CircleDashed, tone: "text-fg-subtle" },
} as const;

function ScenarioRow({ trackSlug, s }: { trackSlug: string; s: ScenarioCard }) {
  const st = s.progress ? STATUS[s.progress] : null;
  return (
    <li>
      <Link
        href={`/drills/${trackSlug}/${s.slug}`}
        transitionTypes={["nav-forward"]}
        className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-1 rounded-sm px-3 py-3 hover:bg-raised md:grid-cols-[6rem_1fr_7rem_8rem]"
      >
        <SevBadge sev={sevNumber(s.difficulty)} />
        <span className="flex min-w-0 flex-col">
          <span className="text-body font-semibold text-fg">{s.title}</span>
          <span className="truncate text-label text-fg-muted">{s.summary}</span>
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

async function TrackContent({ params }: { params: PageProps<"/drills/[track]">["params"] }) {
  const { track: slug } = await params;
  const t = await loadTrack(slug);

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
          {t.title}
        </span>
      </nav>

      <header className="flex flex-wrap items-center gap-5">
        <span className="grid size-12 place-items-center rounded-md bg-raised text-brand-text">
          <ServiceIcon kind={t.icon} className="size-6" />
        </span>
        <div className="flex flex-1 flex-col gap-1">
          <h1 className="text-heading-lg font-semibold tracking-tight text-fg">{t.title}</h1>
          <p className="max-w-2xl text-body-lg text-fg-muted">{t.summary}</p>
        </div>
        {t.progress ? (
          <div className="flex items-center gap-3">
            <MasteryRing value={t.progress.mastery_pct} label={t.title} size={56} />
            <div className="flex flex-col">
              <span className="font-mono text-stat font-semibold text-fg">
                {t.progress.rating ? Math.round(t.progress.rating) : "–"}
              </span>
              <span className="text-caption text-fg-muted">
                {t.progress.rating ? "track rating" : "rated after your first fix"}
              </span>
            </div>
          </div>
        ) : null}
      </header>

      {t.topics_detail.map((topic) => (
        <section key={topic.slug} aria-labelledby={`topic-${topic.slug}`} className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-4 border-b border-border pb-2">
            <h2 id={`topic-${topic.slug}`} className="text-heading-md font-semibold text-fg">
              {topic.title}
            </h2>
          </div>
          {topic.scenarios.length ? (
            <ul className="flex flex-col">
              {topic.scenarios.map((s) => (
                <ScenarioRow key={s.slug} trackSlug={t.slug} s={s} />
              ))}
            </ul>
          ) : (
            <p className="px-3 text-body text-fg-muted">
              Scenarios for this topic arrive with the next content release.
            </p>
          )}
        </section>
      ))}
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
