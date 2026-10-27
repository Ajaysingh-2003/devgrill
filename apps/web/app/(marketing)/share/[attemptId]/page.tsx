import type { Metadata } from "next";
import Link from "next/link";
import { Suspense, cache } from "react";
import { shareCard } from "@devgrill/api-client";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { PageSkeleton } from "@/components/page-skeleton";
import { api, sevNumber, unwrap } from "@/lib/api";
import { shareHeading, shareLine, stopwatch } from "@/lib/share";

const load = cache(async (attemptId: string) =>
  unwrap(shareCard({ client: await api(), path: { attempt_id: attemptId } })),
);

export async function generateMetadata({ params }: PageProps<"/share/[attemptId]">): Promise<Metadata> {
  const card = await load((await params).attemptId);
  const title = shareHeading(card);
  return {
    title,
    description: `${shareLine(card)}. Can you beat it?`,
    // A personal result: shareable by link, never indexed.
    robots: { index: false },
  };
}

async function ShareContent({ params }: { params: PageProps<"/share/[attemptId]">["params"] }) {
  const card = await load((await params).attemptId);
  const hints = card.hints_used === 0 ? "None" : String(card.hints_used);
  const play = card.daily_on ? "/daily" : `/drills/${card.track_slug}/${card.scenario_slug}`;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-8 px-4 py-16 sm:px-6">
      <div className="flex flex-col gap-3">
        {card.daily_on ? <p className="text-label text-fg-muted">{shareHeading(card)}</p> : null}
        <h1 className="font-serif text-display-lg text-fg">Someone fixed “{card.scenario_title}”</h1>
      </div>
      <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-md border border-border bg-border">
        <div className="flex flex-col gap-1 bg-surface p-4">
          <dt className="text-label text-fg-muted">Severity</dt>
          <dd>
            <SevBadge sev={sevNumber(card.difficulty)} showName />
          </dd>
        </div>
        <div className="flex flex-col gap-1 bg-surface p-4">
          <dt className="text-label text-fg-muted">Fixed in</dt>
          <dd className="font-mono text-stat font-semibold text-fg">{stopwatch(card.resolved_in_s)}</dd>
        </div>
        <div className="flex flex-col gap-1 bg-surface p-4">
          <dt className="text-label text-fg-muted">Hints</dt>
          <dd className="font-mono text-stat font-semibold text-fg">{hints}</dd>
        </div>
      </dl>
      <p className="text-body-lg text-fg-muted">
        No spoilers here: what broke and how it was fixed stay secret until you solve it yourself.
      </p>
      <Link
        href={play}
        className="inline-flex h-10 w-fit items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
      >
        {card.daily_on ? "Play today’s drill" : "Try this drill"}
      </Link>
    </div>
  );
}

export default function SharePage({ params }: PageProps<"/share/[attemptId]">) {
  return (
    <Suspense fallback={<PageSkeleton label="Loading the result" />}>
      <ShareContent params={params} />
    </Suspense>
  );
}
