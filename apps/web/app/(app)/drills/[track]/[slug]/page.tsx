import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Fragment, Suspense, cache } from "react";
import { getScenario, type SystemNode as Node } from "@devgrill/api-client";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ServiceIcon } from "@devgrill/ui/icons";
import { ModePicker } from "@/components/mode-picker";
import { PageSkeleton } from "@/components/page-skeleton";
import { PageTransition } from "@/components/page-transition";
import { api, sevNumber, unwrap } from "@/lib/api";

const loadScenario = cache(async (slug: string) =>
  unwrap(getScenario({ client: await api(), path: { slug } })),
);

export async function generateMetadata({ params }: PageProps<"/drills/[track]/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const s = await loadScenario(slug);
  return { title: s.title, description: s.summary };
}

function SystemNode({ node }: { node: Node }) {
  return (
    <span className="flex items-center gap-2.5 rounded-sm border border-border bg-surface px-3 py-2">
      <ServiceIcon kind={node.kind} className="text-fg-muted" />
      <span className="flex flex-col">
        <span className="font-mono text-mono font-medium text-fg">{node.name}</span>
        <span className="text-caption text-fg-subtle">{node.note}</span>
      </span>
    </span>
  );
}

/** T4 Briefing (Field Manual layer). Story, system and goals come from the scenario spec. */
async function BriefingContent({ params }: { params: PageProps<"/drills/[track]/[slug]">["params"] }) {
  const { track: trackSlug, slug } = await params;
  const s = await loadScenario(slug);
  if (s.track_slug !== trackSlug) notFound();

  const system = s.briefing.system ?? [];
  const path = system.filter((n) => n.role !== "side");
  const side = system.filter((n) => n.role === "side");
  const solveRate = s.stats.solve_rate_pct;

  return (
    <div className="grid gap-10 lg:grid-cols-[1fr_20rem]">
      <article className="flex max-w-[42rem] flex-col gap-8">
        <nav aria-label="Breadcrumb" className="text-label text-fg-muted">
          <Link href="/drills" transitionTypes={["nav-back"]} className="hover:text-fg">
            Drills
          </Link>
          <span aria-hidden="true" className="px-1.5 text-fg-subtle">
            /
          </span>
          <Link href={`/drills/${s.track_slug}`} transitionTypes={["nav-back"]} className="hover:text-fg">
            {s.track_title}
          </Link>
          <span aria-hidden="true" className="px-1.5 text-fg-subtle">
            /
          </span>
          <span aria-current="page" className="text-fg">
            {s.title}
          </span>
        </nav>

        <header className="flex flex-col gap-4">
          <p className="flex flex-wrap items-center gap-2 text-label text-fg-muted">
            <SevBadge sev={sevNumber(s.difficulty)} showName />
            <span>About {s.est_minutes} minutes</span>
            {solveRate !== null && solveRate !== undefined ? (
              <>
                <span aria-hidden="true">/</span>
                <span>{solveRate}% of players resolve it</span>
              </>
            ) : null}
          </p>
          <h1 className="font-serif text-display-xl text-fg">{s.title}</h1>
          <p className="font-serif text-[1.375rem] leading-8 text-fg-muted">{s.briefing.story}</p>
        </header>

        {path.length ? (
          <section aria-labelledby="system-title" className="flex flex-col gap-3">
            <h2 id="system-title" className="text-heading-md font-semibold text-fg">
              The system you’re on call for
            </h2>
            <div role="group" className="flex flex-wrap items-center gap-2" aria-label="Request path">
              {path.map((node, i) => (
                <Fragment key={node.name}>
                  {i > 0 ? (
                    <span aria-hidden="true" className="text-fg-subtle">
                      →
                    </span>
                  ) : null}
                  <SystemNode node={node} />
                </Fragment>
              ))}
            </div>
            {side.length ? (
              <p className="flex flex-wrap items-center gap-2 text-label text-fg-muted">
                <span>Also running:</span>
                {side.map((node) => (
                  <SystemNode key={node.name} node={node} />
                ))}
              </p>
            ) : null}
            <p className="text-label text-fg-subtle">
              A real stack runs in your private sandbox for this session. Nothing you do here affects anyone
              else.
            </p>
          </section>
        ) : null}

        <section aria-labelledby="goals-title" className="flex flex-col gap-3">
          <h2 id="goals-title" className="text-heading-md font-semibold text-fg">
            Your goals, in order
          </h2>
          <ol className="flex flex-col gap-3">
            {(s.briefing.goals ?? []).map((goal, i) => (
              <li key={goal.title} className="grid grid-cols-[1.75rem_1fr] gap-3">
                <span className="grid size-7 place-items-center rounded-full bg-raised font-mono text-mono-sm font-semibold text-fg-muted">
                  {i + 1}
                </span>
                <span className="flex flex-col">
                  <span className="text-body-lg font-semibold text-fg">{goal.title}</span>
                  <span className="text-body text-fg-muted">{goal.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>

        <aside className="rounded-md bg-brand-subtle px-5 py-4">
          <h2 className="text-body-lg font-semibold text-fg">There is no single right answer</h2>
          <p className="mt-1 text-body text-fg-muted">
            You are graded on what the system does, not on matching our code. Any fix that keeps the service
            inside its targets during the replay passes. The debrief compares your fix with every other
            approach.
          </p>
        </aside>
      </article>

      <aside className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
        <ModePicker scenarioSlug={s.slug} />
        {s.warmup ? (
          <div className="rounded-md border border-border bg-surface p-4">
            <h2 className="text-body font-semibold text-fg">Not ready yet?</h2>
            <p className="mt-2 text-body">
              <Link
                href={`/drills/${s.warmup.track_slug}/${s.warmup.slug}`}
                className="text-brand-text hover:underline"
              >
                Warm up with {s.warmup.title} ({s.warmup.difficulty.toUpperCase()})
              </Link>
            </p>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

export default function BriefingPage({ params }: PageProps<"/drills/[track]/[slug]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading briefing" />}>
      <PageTransition>
        <BriefingContent params={params} />
      </PageTransition>
    </Suspense>
  );
}
