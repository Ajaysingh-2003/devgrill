import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { CalendarClock } from "lucide-react";
import { dailyChallenge } from "@devgrill/api-client";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { SevBadge } from "@devgrill/ui/components/devgrill/sev-badge";
import { PageHeader } from "@/components/page-header";
import { PageSkeleton } from "@/components/page-skeleton";
import { api, sevNumber } from "@/lib/api";
import { formatCount, timeLeft } from "@/lib/format";

export const metadata: Metadata = { title: "Daily incident" };

async function Daily() {
  const { data: daily } = await dailyChallenge({ client: await api() });
  if (!daily) {
    return (
      <EmptyState
        icon={CalendarClock}
        title="No daily incident yet"
        action={
          <Link href="/drills" className="text-body font-medium text-brand-text hover:underline">
            Browse the drills
          </Link>
        }
      >
        The first one appears as soon as scenarios are published.
      </EmptyState>
    );
  }
  const s = daily.scenario;
  return (
    <section className="flex flex-col gap-4 rounded-md border border-border bg-surface p-6">
      <SevBadge sev={sevNumber(s.difficulty)} showName size="md" />
      <h2 className="font-serif text-display-lg text-fg">{s.title}</h2>
      <p className="text-body-lg text-fg-muted">{s.summary}.</p>
      <p className="text-body text-fg-muted">
        {daily.players ? `${formatCount(daily.players)} engineers have played it today. ` : ""}
        Closes in {timeLeft(daily.ends_at)}.
      </p>
      <Link
        href={`/drills/${s.track_slug}/${s.slug}`}
        className="inline-flex h-10 w-fit items-center rounded-sm bg-brand px-4 text-body font-semibold text-on-brand hover:bg-brand-hover"
      >
        Read the briefing
      </Link>
    </section>
  );
}

export default function DailyPage() {
  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <PageHeader
        title="Daily incident"
        description="One incident a day, the same for everyone. It resets at midnight India time."
      />
      <Suspense fallback={<PageSkeleton label="Loading today’s incident" />}>
        <Daily />
      </Suspense>
    </div>
  );
}
