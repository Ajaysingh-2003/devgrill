import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { PageSkeleton } from "@/components/page-skeleton";
import { PageTransition } from "@/components/page-transition";
import { notFound } from "next/navigation";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { ServiceIcon, type ServiceKind } from "@devgrill/ui/icons";
import { ModePicker } from "@/components/mode-picker";
import { SCENARIOS, scenario, track } from "@/lib/mock";

export function generateStaticParams() {
  return SCENARIOS.map((s) => ({ track: s.track, slug: s.slug }));
}

export async function generateMetadata({ params }: PageProps<"/drills/[track]/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  return { title: scenario(slug)?.title ?? "Scenario" };
}

const SYSTEM: { kind: ServiceKind; name: string; note: string }[] = [
  { kind: "lb", name: "load-gen", note: "sale traffic" },
  { kind: "api", name: "product-api", note: "Python, 4 pods" },
  { kind: "cache", name: "redis", note: "product cache" },
  { kind: "db", name: "postgres", note: "products, inventory" },
  { kind: "worker", name: "worker", note: "orders queue" },
];

function SystemNode({ node }: { node: (typeof SYSTEM)[number] }) {
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

/** T4 Briefing (Field Manual layer). */
async function BriefingContent({ params }: { params: PageProps<"/drills/[track]/[slug]">["params"] }) {
  const { track: trackSlug, slug } = await params;
  const s = scenario(slug);
  const t = track(trackSlug);
  if (!s || !t) notFound();

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
          <Link href={`/drills/${t.slug}`} transitionTypes={["nav-back"]} className="hover:text-fg">
            {t.name}
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
            <SevBadge sev={s.sev} showName />
            <span>About {s.minutes} minutes</span>
            <span aria-hidden="true">/</span>
            <span>{s.solveRate}% of players resolve it</span>
          </p>
          <h1 className="font-serif text-display-xl text-fg">{s.title}</h1>
          <p className="font-serif text-[1.375rem] leading-8 text-fg-muted">
            You are on call for ShopKart. At 8 p.m. the biggest sale of the year goes live. You have just
            finished dinner when your phone buzzes.
          </p>
        </header>

        <section aria-labelledby="system-title" className="flex flex-col gap-3">
          <h2 id="system-title" className="text-heading-md font-semibold text-fg">
            The system you’re on call for
          </h2>
          {/* Request path: traffic → api → its two dependencies; the worker runs beside it. */}
          <div role="group" className="flex flex-wrap items-center gap-2" aria-label="Request path">
            <SystemNode node={SYSTEM[0]!} />
            <span aria-hidden="true" className="text-fg-subtle">
              →
            </span>
            <SystemNode node={SYSTEM[1]!} />
            <span aria-hidden="true" className="text-fg-subtle">
              →
            </span>
            <span className="flex flex-col gap-2">
              <SystemNode node={SYSTEM[2]!} />
              <SystemNode node={SYSTEM[3]!} />
            </span>
          </div>
          <p className="flex flex-wrap items-center gap-2 text-label text-fg-muted">
            <span>Also running:</span>
            <SystemNode node={SYSTEM[4]!} />
          </p>
          <p className="text-label text-fg-subtle">
            A real stack runs in your private sandbox for this session. Nothing you do here affects anyone
            else.
          </p>
        </section>

        <section aria-labelledby="goals-title" className="flex flex-col gap-3">
          <h2 id="goals-title" className="text-heading-md font-semibold text-fg">
            Your goals, in order
          </h2>
          <ol className="flex flex-col gap-3">
            {[
              ["Mitigate", "Get customers back to working pages as fast as you safely can."],
              ["Find the root cause", "Not just what is slow, but why it started now."],
              [
                "Fix it properly",
                "Your fix has to survive verify, which replays the sale at 10x and attacks the weak spots.",
              ],
              ["Write the postmortem", "Your teammates in the war room are waiting for updates."],
            ].map(([goal, detail], i) => (
              <li key={goal} className="grid grid-cols-[1.75rem_1fr] gap-3">
                <span className="grid size-7 place-items-center rounded-full bg-raised font-mono text-mono-sm font-semibold text-fg-muted">
                  {i + 1}
                </span>
                <span className="flex flex-col">
                  <span className="text-body-lg font-semibold text-fg">{goal}</span>
                  <span className="text-body text-fg-muted">{detail}</span>
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
        <div className="rounded-md border border-border bg-surface p-4">
          <h2 className="text-body font-semibold text-fg">Not ready yet?</h2>
          <ul className="mt-2 flex flex-col gap-2 text-body">
            <li>
              <Link href="#" className="text-brand-text hover:underline">
                Read the primer on cache stampedes
              </Link>
            </li>
            <li>
              <Link href={`/drills/${t.slug}/ttl-zero`} className="text-brand-text hover:underline">
                Warm up with TTL zero (SEV4)
              </Link>
            </li>
          </ul>
        </div>
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
